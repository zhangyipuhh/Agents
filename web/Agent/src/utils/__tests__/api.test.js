import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  formatFileSize,
  getFileExtension,
} from '../api.js'

describe('formatFileSize', () => {
  it('returns 0 B for zero bytes', () => {
    expect(formatFileSize(0)).toBe('0 B')
  })

  it('formats bytes correctly', () => {
    expect(formatFileSize(500)).toBe('500 B')
  })

  it('formats kilobytes correctly', () => {
    expect(formatFileSize(1024)).toBe('1.0 KB')
  })

  it('formats megabytes correctly', () => {
    expect(formatFileSize(1024 * 1024)).toBe('1.0 MB')
  })

  it('formats gigabytes correctly', () => {
    expect(formatFileSize(1024 * 1024 * 1024)).toBe('1.0 GB')
  })

  it('formats terabytes correctly', () => {
    expect(formatFileSize(1024 * 1024 * 1024 * 1024)).toBe('1.0 TB')
  })

  it('formats fractional sizes correctly', () => {
    expect(formatFileSize(1536)).toBe('1.5 KB')
  })
})

describe('getFileExtension', () => {
  it('returns extension for normal filename', () => {
    expect(getFileExtension('document.pdf')).toBe('pdf')
  })

  it('returns lowercase extension', () => {
    expect(getFileExtension('document.PDF')).toBe('pdf')
  })

  it('returns empty string for no extension', () => {
    expect(getFileExtension('document')).toBe('')
  })

  it('handles multiple dots', () => {
    expect(getFileExtension('my.document.pdf')).toBe('pdf')
  })

  it('handles hidden files', () => {
    expect(getFileExtension('.gitignore')).toBe('gitignore')
  })
})
