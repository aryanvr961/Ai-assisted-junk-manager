import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FileRecord } from '../data/tempData'

type ScanResult = {
  total_files: number
  exact_duplicates: any[]
  near_duplicates: any[]
  ai_confirmed: any[]
  outdated_files: any[]
  scan_stats: any
  ai_status: string
}

type Props = {
  files: FileRecord[]
  onArchive: (ids: string[], type: 'archive' | 'near' | 'outdated') => void
  scanResults?: ScanResult | null
  isLoading?: boolean
  archivedFiles?: any[]
}

const getTabStyles = (tabId: 'exact' | 'near' | 'outdated', activeTab: 'exact' | 'near' | 'outdated') => {
  const baseClasses = 'px-6 py-4 font-semibold border-b-2 transition whitespace-nowrap'
  const colors = {
    exact: {
      active: 'border-red-600 text-red-700 bg-red-50',
      badge: 'bg-red-200 text-red-800',
      inactive: 'border-transparent text-gray-600 hover:text-gray-800 bg-white'
    },
    near: {
      active: 'border-orange-600 text-orange-700 bg-orange-50',
      badge: 'bg-orange-200 text-orange-800',
      inactive: 'border-transparent text-gray-600 hover:text-gray-800 bg-white'
    },
    outdated: {
      active: 'border-blue-600 text-blue-700 bg-blue-50',
      badge: 'bg-blue-200 text-blue-800',
      inactive: 'border-transparent text-gray-600 hover:text-gray-800 bg-white'
    }
  }
  const isActive = tabId === activeTab
  const tabColor = colors[tabId]
  return {
    tab: `${baseClasses} ${isActive ? tabColor.active : tabColor.inactive}`,
    badge: `inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold ${
      isActive ? tabColor.badge : 'bg-gray-200 text-gray-700'
    }`
  }
}

export default function ScanResults({ files, onArchive, scanResults, isLoading, archivedFiles = [] }: Props) {
  const navigate = useNavigate()
  const [selectedItems, setSelectedItems] = useState<Set<string>>(new Set())
  const [expandArchived, setExpandArchived] = useState(false)
  const [activeTab, setActiveTab] = useState<'exact' | 'near' | 'outdated'>('exact')

  if (!scanResults) {
    return (
      <div className="max-w-6xl mx-auto p-6 text-center">
        <p className="text-gray-600">No scan results. Please run a scan first.</p>
        <button 
          className="mt-4 px-4 py-2 bg-blue-600 text-white rounded"
          onClick={() => navigate('/')}
        >
          Back to Source Selection
        </button>
      </div>
    )
  }

  const handleSelectAll = (type: string) => {
    const newSelected = new Set(selectedItems)
    if (type === 'exact') {
      scanResults.exact_duplicates.forEach(dup => {
        newSelected.add(dup.file2)
      })
    } else if (type === 'near') {
      scanResults.ai_confirmed.forEach(dup => {
        newSelected.add(dup.file2)
      })
    } else if (type === 'outdated') {
      scanResults.outdated_files.forEach(file => {
        newSelected.add(file.fileName)
      })
    }
    setSelectedItems(newSelected)
  }

  const handleArchiveSelected = async (type: 'archive' | 'near' | 'outdated') => {
    const ids = Array.from(selectedItems)
    if (ids.length > 0) {
      await onArchive(ids, type)
      setSelectedItems(new Set())
    }
  }

  // Tab configuration
  const tabs = [
    { id: 'exact' as const, label: 'Exact Duplicates', count: scanResults.scan_stats.exact_matches },
    { id: 'near' as const, label: 'Near Duplicates (AI Verified)', count: scanResults.scan_stats.near_duplicates },
    { id: 'outdated' as const, label: 'Outdated Files', count: scanResults.scan_stats.old_versions }
  ]

  return (
    <div className="max-w-7xl mx-auto p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-4">
          <button
            className="px-3 py-2 bg-gray-300 text-gray-800 rounded hover:bg-gray-400"
            onClick={() => navigate('/')}
          >
            ← Back
          </button>
          <h2 className="text-2xl font-bold">Scan Results</h2>
        </div>
        <div className="text-sm text-gray-600">
          Total Files: <span className="font-semibold text-gray-800">{scanResults.total_files}</span>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="mb-8">
        <div className="flex gap-2 border-b border-gray-200 bg-white rounded-t-lg">
          {tabs.map(tab => {
            const styles = getTabStyles(tab.id, activeTab)
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={styles.tab}
              >
                <span>{tab.label}</span>
                <span className={styles.badge}>
                  {tab.count}
                </span>
              </button>
            )
          })}
        </div>
      </div>

      {/* Archive Control Bar - Always visible when items selected */}
      {selectedItems.size > 0 && (
        <div className="mb-6 p-4 bg-blue-50 border-l-4 border-blue-600 rounded flex items-center justify-between sticky top-6 z-10">
          <span className="font-semibold text-blue-900">{selectedItems.size} file(s) selected for archive</span>
          <button 
            className="px-6 py-2 bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50 font-semibold"
            onClick={() => {
              const hasExact = scanResults.exact_duplicates.some(d => selectedItems.has(d.file2))
              const hasNear = (scanResults.ai_confirmed.length > 0 ? scanResults.ai_confirmed : scanResults.near_duplicates).some(d => selectedItems.has(d.file2))
              const hasOutdated = scanResults.outdated_files.some(f => selectedItems.has(f.fileName))
              
              if (hasExact) handleArchiveSelected('archive')
              else if (hasNear) handleArchiveSelected('near')
              else if (hasOutdated) handleArchiveSelected('outdated')
            }}
            disabled={isLoading}
          >
            Archive Selected
          </button>
        </div>
      )}

      {/* Content Area */}
      <div className="bg-white rounded-b-lg shadow">
        {/* EXACT DUPLICATES TAB */}
        {activeTab === 'exact' && (
          <div className="p-6">
            {scanResults.exact_duplicates.length > 0 ? (
              <>
                <div className="flex justify-between items-center mb-4">
                  <h3 className="text-lg font-semibold text-gray-800">Exact Duplicate Pairs</h3>
                  <button 
                    className="px-4 py-2 text-sm bg-red-100 text-red-700 rounded hover:bg-red-200 font-semibold"
                    onClick={() => handleSelectAll('exact')}
                  >
                    Select All
                  </button>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="text-left border-b bg-gray-50">
                        <th className="px-4 py-3 font-semibold">Select</th>
                        <th className="px-4 py-3 font-semibold">File to Keep</th>
                        <th className="px-4 py-3 font-semibold">File to Archive</th>
                        <th className="px-4 py-3 font-semibold">Type</th>
                      </tr>
                    </thead>
                    <tbody>
                      {scanResults.exact_duplicates.map((dup, idx) => (
                        <tr key={idx} className="border-b hover:bg-gray-50">
                          <td className="px-4 py-3">
                            <input 
                              type="checkbox"
                              checked={selectedItems.has(dup.file2)}
                              onChange={(e) => {
                                const newSelected = new Set(selectedItems)
                                if (e.target.checked) newSelected.add(dup.file2)
                                else newSelected.delete(dup.file2)
                                setSelectedItems(newSelected)
                              }}
                              className="w-4 h-4 cursor-pointer"
                            />
                          </td>
                          <td className="px-4 py-3 font-medium">{dup.file1}</td>
                          <td className="px-4 py-3 text-red-600 font-medium">{dup.file2}</td>
                          <td className="px-4 py-3">
                            <span className="px-2 py-1 bg-red-100 text-red-700 text-xs rounded font-semibold">
                              100% match
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <div className="py-12 text-center">
                <p className="text-gray-600 text-lg">No exact duplicates found</p>
              </div>
            )}
          </div>
        )}

        {/* NEAR DUPLICATES TAB */}
        {activeTab === 'near' && (
          <div className="p-6">
            {(scanResults.ai_confirmed.length > 0 || scanResults.near_duplicates.length > 0) ? (
              <>
                <div className="flex justify-between items-center mb-4">
                  <h3 className="text-lg font-semibold text-gray-800">
                    AI-Verified Near Duplicates
                    {scanResults.ai_confirmed.length === 0 && <span className="text-sm font-normal text-gray-500 ml-2">(Pending verification)</span>}
                  </h3>
                  <button 
                    className="px-4 py-2 text-sm bg-orange-100 text-orange-700 rounded hover:bg-orange-200 font-semibold"
                    onClick={() => {
                      const newSelected = new Set(selectedItems)
                      const dupsToSelect = scanResults.ai_confirmed.length > 0 ? scanResults.ai_confirmed : scanResults.near_duplicates
                      dupsToSelect.forEach(dup => {
                        newSelected.add(dup.file2)
                      })
                      setSelectedItems(newSelected)
                    }}
                  >
                    Select All
                  </button>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="text-left border-b bg-gray-50">
                        <th className="px-4 py-3 font-semibold">Select</th>
                        <th className="px-4 py-3 font-semibold">File to Keep</th>
                        <th className="px-4 py-3 font-semibold">File to Archive</th>
                        <th className="px-4 py-3 font-semibold">Similarity</th>
                        <th className="px-4 py-3 font-semibold">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(() => {
                        const dupsToDisplay = scanResults.ai_confirmed.length > 0 ? scanResults.ai_confirmed : scanResults.near_duplicates
                        return dupsToDisplay.map((dup, idx) => (
                          <tr key={idx} className="border-b hover:bg-gray-50">
                            <td className="px-4 py-3">
                              <input 
                                type="checkbox"
                                checked={selectedItems.has(dup.file2)}
                                onChange={(e) => {
                                  const newSelected = new Set(selectedItems)
                                  if (e.target.checked) newSelected.add(dup.file2)
                                  else newSelected.delete(dup.file2)
                                  setSelectedItems(newSelected)
                                }}
                                className="w-4 h-4 cursor-pointer"
                              />
                            </td>
                            <td className="px-4 py-3 font-medium">{dup.file1}</td>
                            <td className="px-4 py-3 text-orange-600 font-medium">{dup.file2}</td>
                            <td className="px-4 py-3">
                              <span className="font-semibold text-orange-700">{dup.similarity || 85}%</span>
                            </td>
                            <td className="px-4 py-3">
                              {scanResults.ai_confirmed.length > 0 ? (
                                <span className="px-2 py-1 bg-green-100 text-green-700 text-xs rounded font-semibold">
                                  AI Verified
                                </span>
                              ) : (
                                <span className="px-2 py-1 bg-yellow-100 text-yellow-700 text-xs rounded font-semibold">
                                  Pending
                                </span>
                              )}
                            </td>
                          </tr>
                        ))
                      })()}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <div className="py-12 text-center">
                <p className="text-gray-600 text-lg">No near duplicates found</p>
              </div>
            )}
          </div>
        )}

        {/* OUTDATED FILES TAB */}
        {activeTab === 'outdated' && (
          <div className="p-6">
            {scanResults.outdated_files.length > 0 ? (
              <>
                <div className="flex justify-between items-center mb-4">
                  <h3 className="text-lg font-semibold text-gray-800">Outdated Files (180+ days old)</h3>
                  <button 
                    className="px-4 py-2 text-sm bg-blue-100 text-blue-700 rounded hover:bg-blue-200 font-semibold"
                    onClick={() => handleSelectAll('outdated')}
                  >
                    Select All
                  </button>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="text-left border-b bg-gray-50">
                        <th className="px-4 py-3 font-semibold">Select</th>
                        <th className="px-4 py-3 font-semibold">File Name</th>
                        <th className="px-4 py-3 font-semibold">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {scanResults.outdated_files.map((file, idx) => (
                        <tr key={idx} className="border-b hover:bg-gray-50">
                          <td className="px-4 py-3">
                            <input 
                              type="checkbox"
                              checked={selectedItems.has(file.fileName)}
                              onChange={(e) => {
                                const newSelected = new Set(selectedItems)
                                if (e.target.checked) newSelected.add(file.fileName)
                                else newSelected.delete(file.fileName)
                                setSelectedItems(newSelected)
                              }}
                              className="w-4 h-4 cursor-pointer"
                            />
                          </td>
                          <td className="px-4 py-3 font-medium">{file.fileName}</td>
                          <td className="px-4 py-3">
                            <span className="px-2 py-1 bg-blue-100 text-blue-700 text-xs rounded font-semibold">
                              Outdated
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <div className="py-12 text-center">
                <p className="text-gray-600 text-lg">No outdated files found</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* AI Status and Archived Files Section */}
      <div className="mt-8 space-y-6">
        {/* AI Status */}
        <div className="p-4 bg-blue-50 border border-blue-200 rounded">
          <div className="text-sm text-gray-600">AI Analysis Status: <span className="font-semibold text-blue-700">{scanResults.ai_status}</span></div>
        </div>

        {/* Archived Files Section */}
        {archivedFiles.length > 0 && (
          <div className="border border-gray-200 rounded overflow-hidden">
            <button
              onClick={() => setExpandArchived(!expandArchived)}
              className="w-full px-6 py-4 bg-gradient-to-r from-green-50 to-green-100 hover:from-green-100 hover:to-green-200 border-b border-green-200 font-semibold text-green-900 flex items-center justify-between transition"
            >
              <span className="text-lg">Archived Files ({archivedFiles.length})</span>
              <span className={`text-xl transition-transform ${expandArchived ? 'rotate-180' : ''}`}>▼</span>
            </button>

            {expandArchived && (
              <div className="p-6">
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="text-left border-b bg-gray-50">
                        <th className="px-4 py-3 font-semibold">File Name</th>
                        <th className="px-4 py-3 font-semibold">Type</th>
                        <th className="px-4 py-3 font-semibold">Location</th>
                        <th className="px-4 py-3 font-semibold">Archived At</th>
                      </tr>
                    </thead>
                    <tbody>
                      {archivedFiles.map((file, idx) => (
                        <tr key={idx} className="border-b hover:bg-gray-50">
                          <td className="px-4 py-3 font-medium">{file.file || file.fileName}</td>
                          <td className="px-4 py-3">
                            <span className={`px-2 py-1 rounded text-xs font-semibold ${
                              file.type === 'archive' ? 'bg-red-100 text-red-700' :
                              file.type === 'near' ? 'bg-orange-100 text-orange-700' :
                              'bg-blue-100 text-blue-700'
                            }`}>
                              {file.type === 'archive' ? 'Exact Duplicate' :
                               file.type === 'near' ? 'Near Duplicate' :
                               'Outdated'}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-gray-600 text-sm">{file.destination || 'archive/'}</td>
                          <td className="px-4 py-3 text-gray-600 text-sm">{file.timestamp || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
