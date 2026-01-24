import React from 'react'

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

type Props = {
  onToggle: () => void
  show: boolean
  history: HistoryItem[]
  onArchiveHistory?: (scan_id: string) => void
}

export default function HamburgerMenu({ onToggle, show, history, onArchiveHistory }: Props) {
  const formatDate = (dateString: string) => {
    try {
      const date = new Date(dateString)
      return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    } catch {
      return dateString
    }
  }

  return (
    <div>
      <button className="p-2" onClick={onToggle} aria-label="menu">
        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>
      {show && (
        <div className="absolute left-4 top-14 w-80 bg-white shadow-lg rounded p-4 z-50 max-h-96 overflow-y-auto">
          <h4 className="font-semibold mb-3 text-gray-800">Scan History</h4>
          <div className="space-y-3">
            {history.length === 0 ? (
              <div className="text-sm text-gray-500">No scans yet</div>
            ) : (
              history.map((item) => (
                <div key={item.scan_id} className={`p-2 border rounded text-sm ${item.archived ? 'bg-gray-50 border-gray-200' : 'bg-blue-50 border-blue-200'}`}>
                  <div className="flex justify-between items-start mb-1">
                    <div className="font-medium text-gray-700">{item.source_name}</div>
                    {item.archived && <span className="text-xs bg-gray-300 px-2 py-1 rounded text-gray-700">Archived</span>}
                  </div>
                  <div className="text-xs text-gray-600 mb-1">{formatDate(item.timestamp)}</div>
                  <div className="text-xs text-gray-600 mb-2">
                    📁 {item.total_files} files • 🔄 {item.total_duplicates} duplicates
                  </div>
                  <div className="text-xs text-gray-600 mb-2">
                    ✓ Exact: {item.exact_duplicates_count} | ≈ Near: {item.near_duplicates_count} | ⏰ Old: {item.outdated_files_count}
                  </div>
                  {!item.archived && onArchiveHistory && (
                    <button 
                      onClick={() => onArchiveHistory(item.scan_id)}
                      className="text-xs text-blue-600 hover:text-blue-800 font-medium"
                    >
                      Mark as archived
                    </button>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}

