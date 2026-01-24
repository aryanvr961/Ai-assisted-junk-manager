import React, { useMemo, useState, useEffect } from 'react'
import { Routes, Route, useNavigate } from 'react-router-dom'
import SelectDataSource from './screens/SelectDataSource'
import ScanResults from './screens/ScanResults'
import { tempFiles, FileRecord } from './data/tempData'
import HamburgerMenu from './components/HamburgerMenu'
import { executeArchiveWithBackend } from './utils/archive'

const API_BASE_URL = 'http://localhost:5000'

type Screen = 'select' | 'results'

type HistoryItem = {
  scan_id: string
  timestamp: string
  source_type: string
  source_name: string
  total_files: number
  exact_duplicates_count: number
  near_duplicates_count: number
  outdated_files_count: number
  total_duplicates: number
  archived: boolean
}

type ScanResult = {
  total_files: number
  exact_duplicates: any[]
  near_duplicates: any[]
  ai_confirmed: any[]
  outdated_files: any[]
  scan_stats: any
  ai_status: string
  scan_id?: string
}

export default function App() {
  const [screen, setScreen] = useState<Screen>('select')
  const [selectedSource, setSelectedSource] = useState<'local'|'gcs'|null>(null)
  const [selectedFolderPath, setSelectedFolderPath] = useState<string>('')
  const [gcsConfig, setGcsConfig] = useState<{bucket: string; credentials: string} | null>(null)
  const [files, setFiles] = useState<FileRecord[]>(tempFiles)
  const [scanResults, setScanResults] = useState<ScanResult | null>(null)
  const [archivedFiles, setArchivedFiles] = useState<any[]>([])
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [menuOpen, setMenuOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const navigate = useNavigate()

  // Fetch scan history from backend on component mount
  useEffect(() => {
    fetchScanHistory()
  }, [])

  async function fetchScanHistory() {
    try {
      const response = await fetch(`${API_BASE_URL}/api/history`)
      if (response.ok) {
        const data = await response.json()
        if (data.history && data.history.length > 0) {
          setHistory(data.history)
          // Also save to localStorage as backup
          localStorage.setItem('scanHistory', JSON.stringify(data.history))
        } else {
          // Try to load from localStorage
          const savedHistory = localStorage.getItem('scanHistory')
          if (savedHistory) {
            setHistory(JSON.parse(savedHistory))
          }
        }
      } else {
        // Firebase not enabled - try localStorage
        const savedHistory = localStorage.getItem('scanHistory')
        if (savedHistory) {
          setHistory(JSON.parse(savedHistory))
        } else {
          console.warn('Scan history unavailable (Firebase not enabled)')
          setHistory([])
        }
      }
    } catch (err) {
      console.warn('Could not fetch scan history:', err)
      // Try localStorage as fallback
      const savedHistory = localStorage.getItem('scanHistory')
      if (savedHistory) {
        setHistory(JSON.parse(savedHistory))
      }
    }
  }

  async function handleArchiveHistory(scan_id: string) {
    try {
      const response = await fetch(`${API_BASE_URL}/api/history/archive`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scan_id })
      })

      if (response.ok) {
        // Refresh history
        fetchScanHistory()
      }
    } catch (err) {
      console.error('Error archiving history:', err)
    }
  }

  async function handleContinue() {
    if (!selectedSource) return
    
    setIsLoading(true)
    setError(null)
    
    try {
      // Call backend scan API
      const response = await fetch(`${API_BASE_URL}/api/scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source: selectedSource,
          ...(selectedSource === 'local' ? { folder_path: selectedFolderPath || 'data' } : {}),
          ...(selectedSource === 'gcs' ? { gcs_config: gcsConfig } : {})
        })
      })

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}))
        const errorMsg = errData.error || 'Failed to scan files'
        throw new Error(errorMsg)
      }

      const data = await response.json()
      setScanResults(data.data)
      
      // Save scan to localStorage for history
      const historyEntry: HistoryItem = {
        scan_id: data.data.scan_id || `scan_${Date.now()}`,
        timestamp: new Date().toISOString(),
        source_type: selectedSource.toUpperCase(),
        source_name: selectedFolderPath || 'data',
        total_files: data.data.total_files,
        exact_duplicates_count: data.data.scan_stats.exact_matches,
        near_duplicates_count: data.data.scan_stats.near_duplicates,
        outdated_files_count: data.data.scan_stats.old_versions,
        total_duplicates: data.data.scan_stats.total_duplicates,
        archived: false
      }
      
      const savedHistory = localStorage.getItem('scanHistory')
      const historyList: HistoryItem[] = savedHistory ? JSON.parse(savedHistory) : []
      historyList.unshift(historyEntry)
      localStorage.setItem('scanHistory', JSON.stringify(historyList))
      setHistory(historyList)
      
      // Refresh history after scan
      fetchScanHistory()
      
      navigate('/results')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred')
      console.error('Scan error:', err)
    } finally {
      setIsLoading(false)
    }
  }

  async function handleArchive(ids: string[], type: 'archive'|'near'|'outdated') {
    if (ids.length === 0 || !scanResults) return
    
    setIsLoading(true)
    setError(null)

    try {
      // Convert type: 'archive' -> 'exact' for backend consistency
      const backendArchiveType = type === 'archive' ? 'exact' : type
      
      // Step 1: Get archive preview from backend
      const previewResponse = await fetch(`${API_BASE_URL}/api/archive/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          scan_results: scanResults,
          source: selectedSource || 'local',
          folder_path: selectedFolderPath || 'data',
          gcs_config: gcsConfig || undefined
        })
      })

      if (!previewResponse.ok) {
        const errData = await previewResponse.json().catch(() => ({}))
        throw new Error(errData.error || 'Failed to generate archive preview')
      }

      const previewData = await previewResponse.json()
      
      // Step 2: FILTER preview data to ONLY selected files
      // Convert ids array to Set for fast lookup
      const selectedSet = new Set(ids)
      const filteredArchiveActions = {
        exact_duplicates: (previewData.preview.exact_duplicates || []).filter((item: any) => 
          selectedSet.has(item.to_archive)
        ),
        near_duplicates: (previewData.preview.near_duplicates || []).filter((item: any) => 
          selectedSet.has(item.to_archive)
        ),
        outdated: (previewData.preview.outdated || []).filter((item: any) => 
          selectedSet.has(item.fileName)
        )
      }
      
      console.log(`[ARCHIVE] Selected ${ids.length} files, preview had ${(previewData.preview.exact_duplicates || []).length} exact + ${(previewData.preview.near_duplicates || []).length} near + ${(previewData.preview.outdated || []).length} outdated`)
      console.log(`[ARCHIVE] After filtering: exact=${filteredArchiveActions.exact_duplicates.length} near=${filteredArchiveActions.near_duplicates.length} outdated=${filteredArchiveActions.outdated.length}`)

      // Step 3: Execute archive on backend
      const executeResponse = await fetch(`${API_BASE_URL}/api/archive/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          archive_type: backendArchiveType,  // SEND THE CONVERTED TYPE TO BACKEND
          archive_actions: filteredArchiveActions,  // SEND ONLY SELECTED ITEMS
          source: selectedSource || 'local',
          folder_path: selectedFolderPath || 'data',
          gcs_config: gcsConfig || undefined,
          scan_results: scanResults  // Backend needs original to filter properly
        })
      })

      if (!executeResponse.ok) {
        const errData = await executeResponse.json().catch(() => ({}))
        throw new Error(errData.error || 'Failed to execute archive')
      }

      const executeData = await executeResponse.json()

      // Step 4: Use backend's updated_scan_results as the new state (SOURCE OF TRUTH)
      // This is the critical fix: backend filters and returns clean data
      if (executeData.updated_scan_results) {
        setScanResults(executeData.updated_scan_results)
      }

      // Step 5: Track archived files for display
      setArchivedFiles(prevArchived => [
        ...prevArchived,
        ...executeData.data.archived_files.map((f: any) => ({
          file: f.file,
          category: f.category,
          destination: f.destination,
          timestamp: new Date().toLocaleString()
        }))
      ])

      // Step 6: Update localStorage history with latest scan state
      if (scanResults.scan_id) {
        const savedHistory = localStorage.getItem('scanHistory')
        const historyList: HistoryItem[] = savedHistory ? JSON.parse(savedHistory) : []
        const scanIndex = historyList.findIndex(h => h.scan_id === scanResults.scan_id)
        
        if (scanIndex >= 0 && executeData.updated_scan_results) {
          historyList[scanIndex] = {
            ...historyList[scanIndex],
            total_duplicates: executeData.updated_scan_results.scan_stats.total_duplicates,
            exact_duplicates_count: executeData.updated_scan_results.scan_stats.exact_matches,
            near_duplicates_count: executeData.updated_scan_results.scan_stats.near_duplicates,
            outdated_files_count: executeData.updated_scan_results.scan_stats.old_versions,
            archived: true
          }
          localStorage.setItem('scanHistory', JSON.stringify(historyList))
        }
      }

      setSuccess(`✅ Successfully archived ${executeData.data.total_archived} file(s)`)
      setTimeout(() => setSuccess(null), 3000)
      
      // Refresh Firebase history if available
      fetchScanHistory()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Archive failed')
      console.error('Archive error:', err)
    } finally {
      setIsLoading(false)
    }
  }


  return (
    <div className="min-h-screen">
      <div className="bg-white shadow-sm">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <HamburgerMenu 
              onToggle={() => setMenuOpen(v => !v)} 
              show={menuOpen} 
              history={history}
              onArchiveHistory={handleArchiveHistory}
            />
            <div className="font-semibold">Duplicate Detector</div>
          </div>
          <div className="flex items-center gap-2">
            {success && <div className="text-green-600 text-sm font-medium">{success}</div>}
            {error && <div className="text-red-600 text-sm">{error}</div>}
          </div>
        </div>
      </div>

      <div className="py-8">
        <Routes>
          <Route path="/" element={(
            <div>
              <SelectDataSource 
                onSelect={(s, folderPath, gcsConfig) => {
                  setSelectedSource(s)
                  if (folderPath) setSelectedFolderPath(folderPath)
                  if (gcsConfig) setGcsConfig(gcsConfig)
                }} 
                selected={selectedSource}
                selectedFolderPath={selectedFolderPath}
              />
              <div className="max-w-4xl mx-auto px-6 mt-6">
                <div className="flex justify-end">
                  <button
                    className={`px-4 py-2 rounded ${selectedSource ? 'bg-green-600 text-white' : 'bg-gray-300 text-gray-600 cursor-not-allowed'}`}
                    disabled={!selectedSource || isLoading}
                    onClick={handleContinue}
                  >
                    {isLoading ? 'Scanning...' : 'Continue to Scan'}
                  </button>
                </div>
              </div>
            </div>
          )} />
          <Route path="/results" element={
            <ScanResults 
              files={files} 
              onArchive={handleArchive} 
              scanResults={scanResults}
              isLoading={isLoading}
              archivedFiles={archivedFiles}
            />
          } />
        </Routes>
      </div>
    </div>
  )
}
