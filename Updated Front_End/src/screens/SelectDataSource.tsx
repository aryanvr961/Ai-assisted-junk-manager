import React, { useState } from 'react'

type GCSConfig = {
  bucket: string
  credentials: string
}

type Props = {
  onSelect: (source: 'local' | 'gcs', folderPath?: string, gcsConfig?: GCSConfig) => void
  selected?: 'local' | 'gcs' | null
  selectedFolderPath?: string
}

export default function SelectDataSource({ onSelect, selected, selectedFolderPath }: Props) {
  const [showFilePicker, setShowFilePicker] = useState(false)
  const [showGCSForm, setShowGCSForm] = useState(false)
  const [gcsData, setGcsData] = useState<GCSConfig>({ bucket: '', credentials: '' })
  const [testingAuth, setTestingAuth] = useState(false)
  const [authMessage, setAuthMessage] = useState<string | null>(null)
  const [customPath, setCustomPath] = useState('')
  const [showCustomPathInput, setShowCustomPathInput] = useState(false)

  const handleGCSSelect = async () => {
    if (!gcsData.bucket || !gcsData.credentials) {
      setAuthMessage('Please fill in bucket name and credentials')
      return
    }

    setTestingAuth(true)
    setAuthMessage(null)

    try {
      const response = await fetch('http://localhost:5000/api/gcs/test-auth', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ credentials: gcsData.credentials })
      })

      const data = await response.json()

      if (!response.ok) {
        setAuthMessage(`Auth failed: ${data.error}`)
        return
      }

      setAuthMessage(`✅ ${data.message}`)
      setTimeout(() => {
        onSelect('gcs', undefined, gcsData)
        setShowGCSForm(false)
      }, 1000)
    } catch (err) {
      setAuthMessage(`Error: ${err instanceof Error ? err.message : 'Network error'}`)
    } finally {
      setTestingAuth(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto p-6">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold">Select Data Source</h1>
        <p className="text-sm text-gray-600">Choose where your data is stored to start scanning.</p>
      </header>

      <div className="grid grid-cols-2 gap-6">
        <div
          className={`p-6 rounded-lg border cursor-pointer hover:shadow ${selected === 'local' ? 'bg-white border-blue-500 shadow' : 'bg-gray-50 border-gray-200 opacity-95'}`}
          onClick={() => onSelect('local')}
        >
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 bg-blue-100 rounded">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7a2 2 0 012-2h3l2 3h6a2 2 0 012 2v7a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" />
              </svg>
            </div>
            <div>
              <h3 className="font-medium">Local Folder</h3>
              <p className="text-sm text-gray-600">Scan files from your local system (data/ folder).</p>
            </div>
          </div>
          <button
            className="mt-2 px-4 py-2 bg-blue-600 text-white rounded disabled:opacity-60"
            onClick={(e) => { e.stopPropagation(); setShowFilePicker(true) }}
          >
            Select Local Folder
          </button>
          {selected === 'local' && (
            <p className="text-xs text-blue-600 mt-2">✅ Selected: Local Data Folder</p>
          )}
        </div>
        
        {showFilePicker && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg p-6 w-96">
              <h3 className="text-lg font-semibold mb-4">Choose a folder or enter custom path</h3>
              
              {!showCustomPathInput ? (
                <>
                  <div className="space-y-3 mb-4">
                    <div className="p-3 bg-blue-50 rounded border border-blue-200">
                      <p className="text-sm font-medium mb-2">Quick Access:</p>
                      <div
                        className="p-2 hover:bg-blue-100 rounded cursor-pointer mb-2"
                        onClick={() => {
                          onSelect('local', 'data')
                          setShowFilePicker(false)
                        }}
                      >
                        📁 Project Data Folder (./data)
                      </div>
                    </div>

                    <div className="p-3 bg-gray-50 rounded border border-gray-200">
                      <p className="text-sm font-medium mb-2">Or Enter Custom Path:</p>
                      <button 
                        className="w-full px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
                        onClick={() => setShowCustomPathInput(true)}
                      >
                        📂 Browse or Enter Path
                      </button>
                    </div>
                  </div>
                  
                  <div className="flex gap-2">
                    <button 
                      className="flex-1 px-4 py-2 bg-gray-300 rounded hover:bg-gray-400"
                      onClick={() => setShowFilePicker(false)}
                    >
                      Cancel
                    </button>
                    <button 
                      className="flex-1 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
                      onClick={() => setShowCustomPathInput(true)}
                    >
                      Custom Path
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium mb-2">Enter full folder path</label>
                      <p className="text-xs text-gray-600 mb-3">Examples:</p>
                      <ul className="text-xs text-gray-600 mb-3 list-disc list-inside space-y-1">
                        <li>C:\Users\YourName\Downloads</li>
                        <li>D:\MyFiles\Documents</li>
                        <li>\\server\share\folder</li>
                        <li>data (for project data folder)</li>
                      </ul>
                      <input
                        type="text"
                        placeholder="C:\Users\YourName\Downloads"
                        value={customPath}
                        onChange={(e) => setCustomPath(e.target.value)}
                        className="w-full px-3 py-2 border rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                        autoFocus
                      />
                    </div>
                  </div>
                  
                  <div className="mt-4 flex gap-2">
                    <button 
                      className="flex-1 px-4 py-2 bg-gray-300 rounded hover:bg-gray-400"
                      onClick={() => {
                        setShowCustomPathInput(false)
                        setCustomPath('')
                      }}
                    >
                      Back
                    </button>
                    <button 
                      className="flex-1 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-60"
                      onClick={() => {
                        if (customPath.trim()) {
                          onSelect('local', customPath)
                          setShowFilePicker(false)
                          setCustomPath('')
                        }
                      }}
                      disabled={!customPath.trim()}
                    >
                      Select
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        )}

        <div
          className={`p-6 rounded-lg border cursor-pointer hover:shadow ${selected === 'gcs' ? 'bg-white border-blue-500 shadow' : 'bg-gray-50 border-gray-200 opacity-95'}`}
          onClick={() => setShowGCSForm(true)}
        >
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 bg-indigo-100 rounded">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 15a4 4 0 004 4h7a4 4 0 100-8 5 5 0 00-9.9.5" />
              </svg>
            </div>
            <div>
              <h3 className="font-medium">Google Cloud Storage (GCS)</h3>
              <p className="text-sm text-gray-600">Scan files from a cloud storage bucket.</p>
            </div>
          </div>
          <button
            className="mt-2 px-4 py-2 bg-indigo-600 text-white rounded"
            onClick={(e) => { e.stopPropagation(); setShowGCSForm(true) }}
          >
            Configure GCS Bucket
          </button>
          {selected === 'gcs' && (
            <p className="text-xs text-indigo-600 mt-2">✅ GCS Connected</p>
          )}
        </div>
      </div>

      {showGCSForm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-semibold mb-4">Google Cloud Storage Configuration</h3>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">Bucket Name</label>
                <input
                  type="text"
                  placeholder="my-bucket-name"
                  value={gcsData.bucket}
                  onChange={(e) => setGcsData({...gcsData, bucket: e.target.value})}
                  className="w-full px-3 py-2 border rounded focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">Service Account JSON</label>
                <textarea
                  placeholder='{"type": "service_account", "project_id": "...", ...}'
                  value={gcsData.credentials}
                  onChange={(e) => setGcsData({...gcsData, credentials: e.target.value})}
                  className="w-full px-3 py-2 border rounded focus:outline-none focus:ring-2 focus:ring-indigo-500 font-mono text-xs"
                  rows={6}
                />
              </div>

              {authMessage && (
                <div className={`p-3 rounded ${authMessage.startsWith('✅') ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                  {authMessage}
                </div>
              )}
            </div>

            <div className="mt-6 flex gap-2">
              <button
                className="flex-1 px-4 py-2 bg-gray-300 rounded hover:bg-gray-400"
                onClick={() => setShowGCSForm(false)}
              >
                Cancel
              </button>
              <button
                className={`flex-1 px-4 py-2 text-white rounded ${testingAuth ? 'bg-gray-400 cursor-not-allowed' : 'bg-indigo-600 hover:bg-indigo-700'}`}
                onClick={handleGCSSelect}
                disabled={testingAuth}
              >
                {testingAuth ? 'Testing...' : 'Test & Connect'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="mt-8 flex items-center justify-between">
        <p className="text-sm text-gray-500">✅ No files are deleted automatically - only moved to archive/</p>
      </div>
    </div>
  )
}
