import { FileRecord } from '../data/tempData'

const API_BASE_URL = 'http://localhost:5000'

function sortByCreated(files: FileRecord[]) {
  return files.slice().sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime())
}

export function archiveDuplicatesByChecksum(files: FileRecord[], checksum: string) {
  const group = files.filter(f => f.checksum === checksum)
  if (group.length <= 1) return { remaining: files, archivedIds: [] as string[] }
  const sorted = sortByCreated(group)
  const keep = sorted[0]
  const toArchive = sorted.slice(1).map(f => f.id)
  const remaining = files.filter(f => !toArchive.includes(f.id))
  return { remaining, archivedIds: toArchive }
}

export function archiveNearDuplicatesByGroup(files: FileRecord[], groupKey: string) {
  const group = files.filter(f => f.nearGroup === groupKey)
  if (group.length <= 1) return { remaining: files, archivedIds: [] as string[] }
  const sorted = sortByCreated(group)
  const keep = sorted[0]
  const toArchive = sorted.slice(1).map(f => f.id)
  const remaining = files.filter(f => !toArchive.includes(f.id))
  return { remaining, archivedIds: toArchive }
}

export function archiveOutdated(files: FileRecord[]) {
  const toArchive = files.filter(f => f.status === 'outdated').map(f => f.id)
  const remaining = files.filter(f => f.status !== 'outdated')
  return { remaining, archivedIds: toArchive }
}

/**
 * Execute archive with backend API
 * Calls /api/archive/preview followed by /api/archive/execute
 */
export async function executeArchiveWithBackend(
  scanResults: any,
  type: 'archive' | 'near' | 'outdated'
): Promise<{ success: boolean; message: string; archived_count?: number }> {
  try {
    // Step 1: Generate preview
    const previewResponse = await fetch(`${API_BASE_URL}/api/archive/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scan_results: scanResults })
    })

    if (!previewResponse.ok) {
      return { success: false, message: 'Failed to generate archive preview' }
    }

    const previewData = await previewResponse.json()

    // Step 2: Execute archive
    const archiveActions = {
      exact_duplicates: previewData.preview.exact_duplicates || [],
      near_duplicates: previewData.preview.near_duplicates || [],
      outdated: previewData.preview.outdated || []
    }

    const executeResponse = await fetch(`${API_BASE_URL}/api/archive/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ archive_actions: archiveActions })
    })

    if (!executeResponse.ok) {
      return { success: false, message: 'Failed to execute archive' }
    }

    const executeData = await executeResponse.json()

    return {
      success: executeData.success,
      message: `Successfully archived ${executeData.data.total_archived} files`,
      archived_count: executeData.data.total_archived
    }
  } catch (error) {
    return {
      success: false,
      message: `Archive error: ${error instanceof Error ? error.message : 'Unknown error'}`
    }
  }
}

