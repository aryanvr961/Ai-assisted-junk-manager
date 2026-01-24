import { describe, it, expect } from 'vitest'
import { tempFiles } from '../data/tempData'
import { archiveDuplicatesByChecksum, archiveNearDuplicatesByGroup, archiveOutdated } from './archive'

describe('archive utilities', () => {
  it('archives exact duplicates by checksum keeping oldest', () => {
    const files = tempFiles
    const { remaining, archivedIds } = archiveDuplicatesByChecksum(files, 'aaa')
    // for checksum 'aaa' we expect ids '2' and '3' archived, keep '1'
    expect(archivedIds.sort()).toEqual(['2','3'])
    expect(remaining.find(f=>f.id==='1')).toBeDefined()
    expect(remaining.find(f=>f.id==='2')).toBeUndefined()
  })

  it('archives near-duplicates by group keeping oldest', () => {
    const files = tempFiles
    const { remaining, archivedIds } = archiveNearDuplicatesByGroup(files, 'g1')
    expect(archivedIds.length).toBe(1)
    // ensure the oldest of g1 remains
    expect(remaining.some(f=>f.nearGroup==='g1')).toBeTruthy()
  })

  it('archives outdated files', () => {
    const files = tempFiles
    const { remaining, archivedIds } = archiveOutdated(files)
    expect(archivedIds).toContain('4')
    expect(remaining.find(f=>f.id==='4')).toBeUndefined()
  })
})
