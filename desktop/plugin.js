import { ROUTES_AREA, SIDEBAR_NAV_AREA, useQuery } from '@hermes/plugin-sdk'
import { useEffect, useMemo, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const VIEWS = [
  ['overview', 'Overview'],
  ['proposal', 'Proposal'],
  ['diff', 'Diff'],
  ['raw', 'Raw'],
  ['verify', 'Verify']
]

const STORED_TARGETS = [
  ['memory', 'Memory'],
  ['user', 'User']
]

function recordLabel(record) {
  return `${record.action}/${record.target}`
}

function formatCreated(value) {
  const date = new Date(Number(value || 0) * 1000)
  return Number.isNaN(date.getTime()) ? 'Unknown' : date.toLocaleString()
}

function MetaField({ label, value }) {
  return jsxs('div', {
    className: 'min-w-0 rounded border border-(--ui-stroke-secondary) p-2.5',
    children: [
      jsx('div', { className: 'text-[0.6875rem] uppercase tracking-wide text-(--ui-text-tertiary)', children: label }),
      jsx('div', { className: 'mt-1 break-words text-sm', children: value || '—' })
    ]
  })
}

function ContentBlock({ label, text }) {
  if (!text) return null
  return jsxs('section', {
    className: 'mt-3',
    children: [
      jsx('h4', { className: 'mb-1 text-xs font-medium text-(--ui-text-tertiary)', children: label }),
      jsx('div', {
        className: 'whitespace-pre-wrap break-words rounded border border-(--ui-stroke-secondary) bg-(--chrome-action-hover) p-3 text-sm leading-relaxed',
        children: String(text)
      })
    ]
  })
}

function OperationCard({ op, index, total }) {
  const action = String(op?.action || 'unknown')
  const title = total > 1 ? `Operation ${index + 1} · ${action}` : action
  const before = op?.matched_entry || op?.old_text || ''
  const content = op?.content || ''

  return jsxs('section', {
    className: 'rounded border border-(--ui-stroke-secondary) p-3',
    children: [
      jsx('h3', { className: 'text-sm font-semibold capitalize', children: title }),
      action === 'add' ? jsx(ContentBlock, { label: 'Content to add', text: content }) : null,
      action === 'replace' ? jsx(ContentBlock, { label: 'Current entry', text: before }) : null,
      action === 'replace' ? jsx(ContentBlock, { label: 'Replacement', text: content }) : null,
      action === 'remove' ? jsx(ContentBlock, { label: 'Entry to remove', text: before }) : null,
      !['add', 'replace', 'remove'].includes(action)
        ? jsx('pre', {
            className: 'mt-3 overflow-auto whitespace-pre-wrap break-words rounded border border-(--ui-stroke-secondary) p-3 font-mono text-xs',
            children: JSON.stringify(op, null, 2)
          })
        : null
    ]
  })
}

function OverviewView({ detail }) {
  const record = detail.record || {}
  const payload = detail.payload || {}
  const operations = payload.action === 'batch' && Array.isArray(payload.operations) ? payload.operations : [payload]

  return jsxs('div', {
    className: 'min-h-0 flex-1 overflow-auto p-4',
    'data-selectable-text': 'true',
    children: [
      jsx('div', {
        className: 'grid gap-2 sm:grid-cols-2 xl:grid-cols-4',
        children: [
          jsx(MetaField, { label: 'Action', value: record.action }, 'action'),
          jsx(MetaField, { label: 'Target', value: record.target }, 'target'),
          jsx(MetaField, { label: 'Origin', value: record.origin }, 'origin'),
          jsx(MetaField, { label: 'Created', value: formatCreated(record.created_at) }, 'created')
        ]
      }),
      jsxs('section', {
        className: 'mt-4',
        children: [
          jsx('h3', { className: 'mb-1 text-xs font-medium text-(--ui-text-tertiary)', children: 'Summary' }),
          jsx('div', { className: 'text-sm leading-relaxed', children: record.summary || '(no summary)' })
        ]
      }),
      jsx('div', {
        className: 'mt-4 grid gap-3',
        children: operations.map((op, index) => jsx(OperationCard, { op, index, total: operations.length }, index))
      })
    ]
  })
}

function PendingWritesPage({ loadRecords, loadDetail, runDecision, source }) {
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState('')
  const [view, setView] = useState('overview')
  const [busyAction, setBusyAction] = useState('')
  const [feedback, setFeedback] = useState(null)
  const [bulkConfirm, setBulkConfirm] = useState('')

  const listing = useQuery({
    queryKey: [source, 'records'],
    queryFn: loadRecords,
    refetchInterval: 5_000
  })

  const records = listing.data?.records || []
  const missingTargetCount = records.filter(record => record.target_status?.state === 'missing').length
  const blockedApprovalCount = records.filter(record => record.target_status?.can_apply === false).length
  const query = search.trim().toLocaleLowerCase()
  const filtered = useMemo(
    () =>
      query
        ? records.filter(record =>
            `${record.id} ${record.action} ${record.target} ${record.origin} ${record.summary}`
              .toLocaleLowerCase()
              .includes(query)
          )
        : records,
    [records, query]
  )
  const currentId =
    (selected && records.some(record => record.id === selected) && selected) ||
    filtered[0]?.id ||
    records[0]?.id ||
    ''

  const detail = useQuery({
    queryKey: [source, 'record', currentId],
    queryFn: () => loadDetail(currentId),
    enabled: Boolean(currentId),
    refetchInterval: 5_000
  })

  const refresh = () => {
    listing.refetch()
    if (currentId) detail.refetch()
  }

  const decide = async (action, target) => {
    const key = `${action}:${target}`
    setBusyAction(key)
    setFeedback(null)
    try {
      const result = await runDecision(action, target)
      setFeedback({ kind: 'success', message: result?.output || `${action} completed.` })
      setSelected('')
      setBulkConfirm('')
      await listing.refetch()
    } catch (error) {
      setFeedback({
        kind: 'error',
        message: error instanceof Error ? error.message : String(error)
      })
    } finally {
      setBusyAction('')
    }
  }

  if (listing.isError) {
    return jsxs('div', {
      className: 'flex h-full flex-col items-center justify-center gap-3 p-8 text-center',
      children: [
        jsx('div', { className: 'text-base font-medium', children: 'Memory Review backend unavailable' }),
        jsx('div', {
          className: 'max-w-lg text-sm text-(--ui-text-tertiary)',
          children: 'Enable the Agent half of memory-review for this profile, then retry.'
        }),
        jsx('button', {
          type: 'button',
          className: 'rounded border border-(--ui-stroke-secondary) px-3 py-1.5 text-sm hover:bg-(--chrome-action-hover)',
          onClick: refresh,
          children: 'Retry'
        })
      ]
    })
  }

  return jsxs('div', {
    className: 'flex h-full min-h-0 flex-col',
    children: [
      jsxs('header', {
        className: 'flex flex-wrap items-center gap-3 border-b border-(--ui-stroke-secondary) px-4 py-3',
        children: [
          jsxs('div', {
            className: 'min-w-0 flex-1',
            children: [
              jsx('h1', { className: 'text-base font-semibold', children: 'Memory Review' }),
              jsx('p', {
                className: 'text-xs text-(--ui-text-tertiary)',
                children: 'Review and resolve pending Hermes memory writes'
              })
            ]
          }),
          jsx('span', {
            className: 'rounded-full border border-(--ui-stroke-secondary) px-2 py-0.5 text-[0.6875rem] text-(--ui-text-tertiary)',
            children: `${listing.data?.count ?? 0} pending${missingTargetCount ? ` · ${missingTargetCount} obsolete` : ''}`
          }),
          jsx('button', {
            type: 'button',
            className: 'rounded border border-(--ui-stroke-secondary) px-2.5 py-1.5 text-xs hover:bg-(--chrome-action-hover)',
            onClick: refresh,
            children: listing.isFetching ? 'Refreshing…' : 'Refresh'
          })
        ]
      }),
      records.length
        ? bulkConfirm
          ? jsxs('div', {
              className: 'flex flex-wrap items-center gap-2 border-b border-(--ui-stroke-secondary) px-4 py-2 text-xs',
              children: [
                jsx('span', {
                  className: 'mr-auto text-(--ui-text-tertiary)',
                  children: `${bulkConfirm === 'approve' ? 'Approve' : 'Reject'} all ${records.length} pending write(s)?`
                }),
                jsx('button', {
                  type: 'button',
                  disabled: Boolean(busyAction) || (bulkConfirm === 'approve' && blockedApprovalCount > 0),
                  onClick: () => decide(bulkConfirm, 'all'),
                  className: `rounded border border-(--ui-stroke-secondary) px-2.5 py-1 ${
                    bulkConfirm === 'reject' ? 'text-(--ui-danger,#f87171)' : ''
                  } hover:bg-(--chrome-action-hover) disabled:opacity-50`,
                  children: busyAction ? 'Working…' : `Confirm ${bulkConfirm} all`
                }),
                jsx('button', {
                  type: 'button',
                  disabled: Boolean(busyAction),
                  onClick: () => setBulkConfirm(''),
                  className: 'rounded px-2.5 py-1 text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) disabled:opacity-50',
                  children: 'Cancel'
                })
              ]
            })
          : jsxs('div', {
              className: 'flex flex-wrap items-center gap-2 border-b border-(--ui-stroke-secondary) px-4 py-2',
              children: [
                jsx('span', { className: 'mr-auto text-xs text-(--ui-text-tertiary)', children: 'Bulk actions' }),
                jsx('button', {
                  type: 'button',
                  disabled: Boolean(busyAction) || blockedApprovalCount > 0,
                  title: blockedApprovalCount ? 'Resolve obsolete or unverifiable proposals before approving all.' : undefined,
                  onClick: () => setBulkConfirm('approve'),
                  className: 'rounded border border-(--ui-stroke-secondary) px-2.5 py-1 text-xs hover:bg-(--chrome-action-hover) disabled:opacity-50',
                  children: 'Approve all'
                }),
                jsx('button', {
                  type: 'button',
                  disabled: Boolean(busyAction),
                  onClick: () => setBulkConfirm('reject'),
                  className: 'rounded border border-(--ui-stroke-secondary) px-2.5 py-1 text-xs text-(--ui-danger,#f87171) hover:bg-(--chrome-action-hover) disabled:opacity-50',
                  children: 'Reject all'
                })
              ]
            })
        : null,
      jsxs('div', {
        className: 'grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[minmax(15rem,22rem)_1fr]',
        children: [
          jsxs('aside', {
            className: 'flex min-h-0 flex-col border-b border-(--ui-stroke-secondary) md:border-b-0 md:border-r',
            children: [
              jsx('div', {
                className: 'p-3',
                children: jsx('input', {
                  type: 'search',
                  value: search,
                  onChange: event => setSearch(event.target.value),
                  placeholder: 'Search pending memory…',
                  'aria-label': 'Search pending memory',
                  className: 'w-full rounded border border-(--ui-stroke-secondary) bg-transparent px-2.5 py-1.5 text-sm outline-none focus:border-(--ui-accent)'
                })
              }),
              listing.isLoading
                ? jsx('div', { className: 'p-4 text-sm text-(--ui-text-tertiary)', children: 'Loading…' })
                : filtered.length === 0
                  ? jsx('div', {
                      className: 'p-4 text-sm text-(--ui-text-tertiary)',
                      children: records.length ? 'No matches.' : 'No pending memory writes.'
                    })
                  : jsx('div', {
                      className: 'min-h-0 flex-1 overflow-auto px-2 pb-2',
                      children: filtered.map(record =>
                        jsxs('button', {
                          type: 'button',
                          onClick: () => setSelected(record.id),
                          className: `mb-1 block w-full rounded px-2.5 py-2 text-left transition-colors ${
                            currentId === record.id
                              ? 'bg-(--chrome-action-hover)'
                              : 'hover:bg-(--chrome-action-hover)'
                          }`,
                          children: [
                            jsxs('div', {
                              className: 'flex items-center gap-2',
                              children: [
                                jsx('span', { className: 'truncate text-xs font-medium', children: record.id }),
                                jsx('span', {
                                  className: 'ml-auto shrink-0 text-[0.6875rem] text-(--ui-text-tertiary)',
                                  children: recordLabel(record)
                                })
                              ]
                            }),
                            jsx('div', {
                              className: 'mt-1 line-clamp-2 text-xs text-(--ui-text-tertiary)',
                              children: record.summary || '(no summary)'
                            }),
                            record.origin === 'background_review'
                              ? jsx('div', {
                                  className: 'mt-1 text-[0.6875rem] text-(--ui-text-quaternary)',
                                  children: 'automatic review'
                                })
                              : null,
                            record.target_status?.state === 'missing'
                              ? jsx('div', {
                                  className: 'mt-1 text-[0.6875rem] text-(--ui-danger,#f87171)',
                                  children: 'target missing · obsolete proposal'
                                })
                              : null
                          ]
                        }, record.id)
                      )
                    })
            ]
          }),
          jsxs('main', {
            className: 'flex min-h-0 min-w-0 flex-col',
            children: [
              currentId
                ? jsxs('div', {
                    className: 'flex flex-wrap items-center gap-1 border-b border-(--ui-stroke-secondary) px-3 py-2',
                    children: [
                      ...VIEWS.map(([id, label]) =>
                        jsx('button', {
                          type: 'button',
                          onClick: () => setView(id),
                          'aria-pressed': view === id,
                          className: `rounded px-2.5 py-1 text-xs ${
                            view === id
                              ? 'bg-(--chrome-action-hover) font-medium'
                              : 'text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover)'
                          }`,
                          children: label
                        }, id)
                      ),
                      jsx('span', { className: 'min-w-2 flex-1' }),
                      jsx('button', {
                        type: 'button',
                        disabled:
                          Boolean(busyAction) ||
                          detail.isLoading ||
                          !detail.data ||
                          detail.data.record?.target_status?.can_apply === false,
                        onClick: () => decide('approve', currentId),
                        className: 'rounded border border-(--ui-stroke-secondary) px-2.5 py-1 text-xs hover:bg-(--chrome-action-hover) disabled:opacity-50',
                        children:
                          detail.data?.record?.target_status?.can_apply === false
                            ? 'Cannot approve'
                            : busyAction === `approve:${currentId}`
                              ? 'Approving…'
                              : 'Approve'
                      }, 'approve'),
                      jsx('button', {
                        type: 'button',
                        disabled: Boolean(busyAction),
                        onClick: () => decide('reject', currentId),
                        className: 'rounded border border-(--ui-stroke-secondary) px-2.5 py-1 text-xs text-(--ui-danger,#f87171) hover:bg-(--chrome-action-hover) disabled:opacity-50',
                        children:
                          busyAction === `reject:${currentId}`
                            ? detail.data?.record?.target_status?.state === 'missing' ? 'Deleting…' : 'Rejecting…'
                            : detail.data?.record?.target_status?.state === 'missing' ? 'Delete obsolete' : 'Reject'
                      }, 'reject')
                    ]
                  })
                : null,
              feedback
                ? jsx('div', {
                    className: `border-b border-(--ui-stroke-secondary) px-4 py-2 text-xs ${
                      feedback.kind === 'error' ? 'text-(--ui-danger,#f87171)' : 'text-(--ui-text-tertiary)'
                    }`,
                    children: feedback.message
                  })
                : null,
              detail.data?.record?.target_status?.state === 'missing'
                ? jsx('div', {
                    className: 'border-b border-(--ui-stroke-secondary) px-4 py-2 text-xs text-(--ui-danger,#f87171)',
                    children:
                      detail.data.record.target_status.message ||
                      'Target entry no longer exists. Reject this obsolete proposal to delete it.'
                  })
                : detail.data?.record?.target_status?.state === 'unverifiable'
                  ? jsx('div', {
                      className: 'border-b border-(--ui-stroke-secondary) px-4 py-2 text-xs text-(--ui-danger,#f87171)',
                      children: detail.data.record.target_status.message
                    })
                  : null,
              detail.isError
                ? jsx('div', {
                    className: 'p-4 text-sm text-(--ui-text-tertiary)',
                    children: 'Could not load this pending record. It may have been resolved since the last refresh.'
                  })
                : detail.isLoading && currentId
                  ? jsx('div', { className: 'p-4 text-sm text-(--ui-text-tertiary)', children: 'Loading record…' })
                  : currentId && detail.data
                    ? view === 'overview'
                      ? jsx(OverviewView, { detail: detail.data })
                      : jsx('pre', {
                          className: 'min-h-0 flex-1 overflow-auto whitespace-pre-wrap break-words p-4 font-mono text-xs leading-relaxed',
                          'data-selectable-text': 'true',
                          children: detail.data[view] || ''
                        })
                    : jsx('div', {
                        className: 'flex min-h-0 flex-1 items-center justify-center p-6 text-sm text-(--ui-text-tertiary)',
                        children: 'Select a pending memory write to inspect it.'
                      })
            ]
          })
        ]
      }),
      listing.data?.issues?.length
        ? jsx('div', {
            className: 'border-t border-(--ui-stroke-secondary) px-4 py-2 text-xs text-(--ui-text-tertiary)',
            children: `${listing.data.issues.length} malformed pending file(s) were skipped.`
          })
        : null
    ]
  })
}

function StoredMemoryPage({ loadStoredMemory, saveStoredMemory, addStoredMemory, deleteStoredMemory, requestCompaction, applyCompaction, source }) {
  const [target, setTarget] = useState('memory')
  const [search, setSearch] = useState('')
  const [selectedText, setSelectedText] = useState('')
  const [draft, setDraft] = useState('')
  const [adding, setAdding] = useState(false)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState(false)
  const [compacting, setCompacting] = useState(false)
  const [compactionElapsed, setCompactionElapsed] = useState(0)
  const [applyingCompaction, setApplyingCompaction] = useState(false)
  const [compactionPreview, setCompactionPreview] = useState(null)
  const [feedback, setFeedback] = useState(null)

  const stored = useQuery({
    queryKey: [source, 'stored-memory'],
    queryFn: loadStoredMemory,
    refetchInterval: 5_000
  })

  const targetData = stored.data?.targets?.[target] || { count: 0, entries: [] }
  const entries = targetData.entries || []
  const query = search.trim().toLocaleLowerCase()
  const filtered = useMemo(
    () =>
      query
        ? entries.filter(entry => String(entry.content || '').toLocaleLowerCase().includes(query))
        : entries,
    [entries, query]
  )
  const selectedEntry = selectedText ? entries.find(entry => entry.content === selectedText) : null
  const current = adding
    ? null
    : selectedText
      ? selectedEntry || { index: -1, content: selectedText, stale: true }
      : filtered[0] || entries[0] || null

  useEffect(() => {
    if (!adding) setDraft(current?.content || '')
  }, [target, adding, current?.content])

  useEffect(() => {
    if (!compacting) return undefined
    const startedAt = Date.now()
    const updateElapsed = () => setCompactionElapsed(Math.floor((Date.now() - startedAt) / 1000))
    updateElapsed()
    const timer = setInterval(updateElapsed, 1000)
    return () => clearInterval(timer)
  }, [compacting])

  const selectTarget = nextTarget => {
    setTarget(nextTarget)
    setSelectedText('')
    setSearch('')
    setAdding(false)
    setDeleteConfirm(false)
    setCompactionPreview(null)
    setFeedback(null)
  }

  const selectEntry = content => {
    setAdding(false)
    setDeleteConfirm(false)
    setSelectedText(content)
  }

  const beginAdd = () => {
    setAdding(true)
    setSelectedText('')
    setDraft('')
    setDeleteConfirm(false)
    setCompactionPreview(null)
    setFeedback(null)
  }

  const add = async () => {
    const content = draft.trim()
    if (!content) return
    setSaving(true)
    setFeedback(null)
    try {
      const result = await addStoredMemory(target, content)
      setFeedback({ kind: 'success', message: result?.result?.message || 'Memory entry added.' })
      setAdding(false)
      setSelectedText(content)
      await stored.refetch()
    } catch (error) {
      setFeedback({
        kind: 'error',
        message: error instanceof Error ? error.message : String(error)
      })
    } finally {
      setSaving(false)
    }
  }

  const save = async () => {
    if (!current) return
    setSaving(true)
    setFeedback(null)
    try {
      const result = await saveStoredMemory(target, current.content, draft)
      setFeedback({ kind: 'success', message: result?.result?.message || 'Memory entry updated.' })
      setSelectedText(draft.trim())
      setDeleteConfirm(false)
      await stored.refetch()
    } catch (error) {
      setFeedback({
        kind: 'error',
        message: error instanceof Error ? error.message : String(error)
      })
    } finally {
      setSaving(false)
    }
  }

  const remove = async () => {
    if (!current || current.stale) return
    if (!deleteConfirm) {
      setDeleteConfirm(true)
      return
    }
    setDeleting(true)
    setFeedback(null)
    try {
      const result = await deleteStoredMemory(target, current.content)
      setFeedback({ kind: 'success', message: result?.result?.message || 'Memory entry removed.' })
      setSelectedText('')
      setDeleteConfirm(false)
      await stored.refetch()
    } catch (error) {
      setFeedback({
        kind: 'error',
        message: error instanceof Error ? error.message : String(error)
      })
    } finally {
      setDeleting(false)
    }
  }

  const compact = async () => {
    setCompactionElapsed(0)
    setCompacting(true)
    setCompactionPreview(null)
    setFeedback(null)
    try {
      const preview = await requestCompaction(target)
      setCompactionPreview(preview)
    } catch (error) {
      setFeedback({
        kind: 'error',
        message: error instanceof Error ? error.message : String(error)
      })
    } finally {
      setCompacting(false)
    }
  }

  const applyPreview = async () => {
    if (!compactionPreview) return
    setApplyingCompaction(true)
    setFeedback(null)
    try {
      const result = await applyCompaction(
        compactionPreview.target,
        compactionPreview.source_fingerprint,
        compactionPreview.proposed_entries
      )
      setFeedback({ kind: 'success', message: result?.result?.message || 'Memory compaction applied.' })
      setCompactionPreview(null)
      setSelectedText('')
      await stored.refetch()
    } catch (error) {
      setFeedback({
        kind: 'error',
        message: error instanceof Error ? error.message : String(error)
      })
    } finally {
      setApplyingCompaction(false)
    }
  }

  if (stored.isError) {
    return jsxs('div', {
      className: 'flex h-full flex-col items-center justify-center gap-3 p-8 text-center',
      children: [
        jsx('div', { className: 'text-base font-medium', children: 'Stored memory unavailable' }),
        jsx('div', {
          className: 'max-w-lg text-sm text-(--ui-text-tertiary)',
          children: 'Enable the Agent half of memory-review for this profile, then retry.'
        }),
        jsx('button', {
          type: 'button',
          className: 'rounded border border-(--ui-stroke-secondary) px-3 py-1.5 text-sm hover:bg-(--chrome-action-hover)',
          onClick: () => stored.refetch(),
          children: 'Retry'
        })
      ]
    })
  }

  return jsxs('div', {
    className: 'flex h-full min-h-0 flex-col overflow-hidden',
    children: [
      jsxs('header', {
        className: 'flex shrink-0 flex-wrap items-center gap-3 border-b border-(--ui-stroke-secondary) px-4 py-3',
        children: [
          jsxs('div', {
            className: 'min-w-0 flex-1',
            children: [
              jsx('h1', { className: 'text-base font-semibold', children: 'Stored memory' }),
              jsx('p', {
                className: 'text-xs text-(--ui-text-tertiary)',
                children: 'Inspect, edit, and compact Hermes built-in memory entries'
              })
            ]
          }),
          jsx('span', {
            className: 'rounded-full border border-(--ui-stroke-secondary) px-2 py-0.5 text-[0.6875rem] text-(--ui-text-tertiary)',
            children: `${targetData.count ?? 0} entries`
          }),
          jsx('span', {
            className: 'rounded-full border border-(--ui-stroke-secondary) px-2 py-0.5 text-[0.6875rem] text-(--ui-text-tertiary)',
            children: `~${targetData.estimated_tokens ?? 0} / ~${targetData.estimated_token_limit ?? 0} tokens estimated · ${targetData.usage_percent ?? 0}% used`
          }),
          jsx('span', {
            className: 'rounded-full border border-(--ui-stroke-secondary) px-2 py-0.5 text-[0.6875rem] text-(--ui-text-tertiary)',
            children: `${targetData.used_chars ?? 0} / ${targetData.char_limit ?? 0} chars`
          }),
          jsx('button', {
            type: 'button',
            disabled: compacting || applyingCompaction || saving || deleting,
            className: 'rounded border border-(--ui-stroke-secondary) px-2.5 py-1.5 text-xs hover:bg-(--chrome-action-hover) disabled:opacity-50',
            onClick: beginAdd,
            children: 'Add entry'
          }),
          jsx('button', {
            type: 'button',
            disabled: compacting || applyingCompaction || saving || deleting || !targetData.count,
            className: 'rounded border border-(--ui-stroke-secondary) px-2.5 py-1.5 text-xs hover:bg-(--chrome-action-hover) disabled:opacity-50',
            onClick: compact,
            children: compacting ? 'Compacting…' : 'Compact with AI'
          }),
          jsx('button', {
            type: 'button',
            className: 'rounded border border-(--ui-stroke-secondary) px-2.5 py-1.5 text-xs hover:bg-(--chrome-action-hover)',
            onClick: () => stored.refetch(),
            children: stored.isFetching ? 'Refreshing…' : 'Refresh'
          })
        ]
      }),
      jsx('div', {
        className: 'flex shrink-0 flex-wrap gap-1 border-b border-(--ui-stroke-secondary) px-3 py-2',
        children: STORED_TARGETS.map(([id, label]) =>
          jsx('button', {
            type: 'button',
            disabled: compacting || applyingCompaction || saving || deleting,
            onClick: () => selectTarget(id),
            'aria-pressed': target === id,
            className: `rounded px-2.5 py-1 text-xs ${
              target === id
                ? 'bg-(--chrome-action-hover) font-medium'
                : 'text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover)'
            }`,
            children: `${label} · ${stored.data?.targets?.[id]?.usage_percent ?? 0}% used`
          }, id)
        )
      }),
      feedback
        ? jsx('div', {
            className: `shrink-0 border-b border-(--ui-stroke-secondary) px-4 py-2 text-xs ${
              feedback.kind === 'error' ? 'text-(--ui-danger,#f87171)' : 'text-(--ui-text-tertiary)'
            }`,
            children: feedback.message
          })
        : null,
      compacting
        ? jsxs('section', {
            className: 'shrink-0 border-b border-(--ui-stroke-secondary) px-4 py-3',
            children: [
              jsxs('div', {
                className: 'flex items-center gap-2 text-sm font-medium',
                children: [
                  jsx('span', { className: 'inline-block h-2 w-2 animate-pulse rounded-full bg-(--ui-accent)' }),
                  jsx('span', { children: 'AI compaction in progress' })
                ]
              }),
              jsx('div', {
                className: 'mt-1 text-xs text-(--ui-text-tertiary)',
                children: `Request sent to Hermes · ${compactionElapsed}s elapsed`
              }),
              jsx('div', {
                className: 'mt-2 h-1.5 overflow-hidden rounded-full bg-(--chrome-action-hover)',
                children: jsx('div', {
                  className: 'h-full w-2/3 animate-pulse rounded-full bg-(--ui-accent)'
                })
              }),
              jsx('div', {
                className: 'mt-2 text-xs text-(--ui-text-tertiary)',
                children: 'Hermes is generating and validating a smaller proposal; if needed, it will automatically retry with a stricter compression budget.'
              })
            ]
          })
        : null,
      compactionPreview
        ? jsxs('section', {
            className: 'flex max-h-[40vh] shrink-0 flex-col overflow-hidden border-b border-(--ui-stroke-secondary) bg-(--chrome-action-hover)',
            children: [
              jsxs('div', {
                className: 'flex shrink-0 flex-wrap items-center gap-2 px-4 pt-3',
                children: [
                  jsx('h2', { className: 'mr-auto text-sm font-semibold', children: 'AI compaction preview' }),
                  jsx('span', {
                    className: 'text-xs text-(--ui-text-tertiary)',
                    children: `~${compactionPreview.before_tokens} → ~${compactionPreview.after_tokens} tokens estimated`
                  }),
                  jsx('span', {
                    className: 'text-xs text-(--ui-text-tertiary)',
                    children: `${compactionPreview.before_entry_count ?? '?'} → ${compactionPreview.after_entry_count ?? '?'} entries · ${compactionPreview.reduction_percent ?? '?'}% smaller`
                  }),
                  jsx('span', {
                    className: 'text-xs text-(--ui-text-tertiary)',
                    children: [compactionPreview.provider, compactionPreview.model].filter(Boolean).join(' / ') || 'Default model'
                  }),
                  jsx('span', {
                    className: 'text-xs text-(--ui-text-tertiary)',
                    children: `${compactionPreview.attempts || 1} AI attempt${(compactionPreview.attempts || 1) === 1 ? '' : 's'}`
                  })
                ]
              }),
              jsx('div', {
                className: 'min-h-0 flex-1 space-y-2 overflow-auto px-4 py-3',
                children: (compactionPreview.proposed_entries || []).map((entry, index) =>
                  jsxs('div', {
                    className: 'rounded border border-(--ui-stroke-secondary) bg-(--ui-bg-primary,transparent) p-2.5',
                    children: [
                      jsx('div', {
                        className: 'mb-1 text-[0.6875rem] uppercase tracking-wide text-(--ui-text-tertiary)',
                        children: `Proposed entry ${index + 1}`
                      }),
                      jsx('div', { className: 'whitespace-pre-wrap break-words text-sm', children: entry })
                    ]
                  }, `compact:${index}`)
                )
              }),
              jsxs('div', {
                className: 'flex shrink-0 flex-wrap items-center gap-2 border-t border-(--ui-stroke-secondary) px-4 py-3',
                children: [
                  jsx('button', {
                    type: 'button',
                    disabled: applyingCompaction,
                    onClick: applyPreview,
                    className: 'rounded border border-(--ui-stroke-secondary) px-2.5 py-1.5 text-xs font-medium hover:bg-(--chrome-action-hover) disabled:opacity-50',
                    children: applyingCompaction ? 'Applying…' : 'Apply compaction'
                  }),
                  jsx('button', {
                    type: 'button',
                    disabled: applyingCompaction,
                    onClick: () => setCompactionPreview(null),
                    className: 'rounded border border-(--ui-stroke-secondary) px-2.5 py-1.5 text-xs hover:bg-(--chrome-action-hover) disabled:opacity-50',
                    children: 'Cancel preview'
                  }),
                  jsx('span', {
                    className: 'text-xs text-(--ui-text-tertiary)',
                    children: 'No stored memory changes until Apply compaction is pressed.'
                  })
                ]
              })
            ]
          })
        : null,
      jsxs('div', {
        className: 'grid min-h-0 flex-1 grid-cols-1 overflow-hidden md:grid-cols-[minmax(15rem,22rem)_1fr]',
        children: [
          jsxs('aside', {
            className: 'flex min-h-0 flex-col border-b border-(--ui-stroke-secondary) md:border-b-0 md:border-r',
            children: [
              jsx('div', {
                className: 'p-3',
                children: jsx('input', {
                  type: 'search',
                  value: search,
                  onChange: event => setSearch(event.target.value),
                  placeholder: 'Search stored memory',
                  'aria-label': 'Search stored memory',
                  className: 'w-full rounded border border-(--ui-stroke-secondary) bg-transparent px-2.5 py-1.5 text-sm outline-none focus:border-(--ui-accent)'
                })
              }),
              stored.isLoading
                ? jsx('div', { className: 'p-4 text-sm text-(--ui-text-tertiary)', children: 'Loading…' })
                : filtered.length === 0
                  ? jsx('div', {
                      className: 'p-4 text-sm text-(--ui-text-tertiary)',
                      children: entries.length ? 'No matches.' : `No ${target} entries.`
                    })
                  : jsx('div', {
                      className: 'min-h-0 flex-1 overflow-auto px-2 pb-2',
                      children: filtered.map(entry =>
                        jsx('button', {
                          type: 'button',
                          onClick: () => selectEntry(entry.content),
                          className: `mb-1 block w-full rounded px-2.5 py-2 text-left transition-colors ${
                            current?.content === entry.content
                              ? 'bg-(--chrome-action-hover)'
                              : 'hover:bg-(--chrome-action-hover)'
                          }`,
                          children: jsx('div', {
                            className: 'line-clamp-3 whitespace-pre-wrap break-words text-xs text-(--ui-text-tertiary)',
                            children: entry.content || '(empty entry)'
                          })
                        }, `${target}:${entry.index}`)
                      )
                    })
            ]
          }),
          adding
            ? jsxs('main', {
                className: 'flex min-h-0 min-w-0 flex-col',
                children: [
                  jsxs('div', {
                    className: 'flex flex-wrap items-center gap-2 border-b border-(--ui-stroke-secondary) px-4 py-2',
                    children: [
                      jsx('span', {
                        className: 'mr-auto text-xs text-(--ui-text-tertiary)',
                        children: `New ${target === 'memory' ? 'MEMORY.md' : 'USER.md'} entry`
                      }),
                      jsx('button', {
                        type: 'button',
                        disabled: saving,
                        onClick: () => setAdding(false),
                        className: 'rounded border border-(--ui-stroke-secondary) px-2.5 py-1 text-xs hover:bg-(--chrome-action-hover) disabled:opacity-50',
                        children: 'Cancel'
                      }),
                      jsx('button', {
                        type: 'button',
                        disabled: saving || !draft.trim(),
                        onClick: add,
                        className: 'rounded border border-(--ui-stroke-secondary) px-2.5 py-1 text-xs font-medium hover:bg-(--chrome-action-hover) disabled:opacity-50',
                        children: saving ? 'Adding…' : 'Add entry'
                      })
                    ]
                  }),
                  jsx('textarea', {
                    value: draft,
                    onChange: event => {
                      setDraft(event.target.value)
                      setDeleteConfirm(false)
                    },
                    'aria-label': `Add ${target} memory entry`,
                    placeholder: 'Enter a durable memory entry…',
                    className: 'min-h-0 flex-1 resize-none bg-transparent p-4 text-sm leading-relaxed outline-none',
                    spellCheck: false
                  }),
                  jsx('div', {
                    className: 'border-t border-(--ui-stroke-secondary) px-4 py-2 text-xs text-(--ui-text-tertiary)',
                    children: 'Adding delegates to Hermes MemoryStore validation, limits, locking, and persistence.'
                  })
                ]
              })
            : current
              ? jsxs('main', {
                className: 'flex min-h-0 min-w-0 flex-col',
                children: [
                  jsxs('div', {
                    className: 'flex flex-wrap items-center gap-2 border-b border-(--ui-stroke-secondary) px-4 py-2',
                    children: [
                      jsx('span', {
                        className: 'mr-auto text-xs text-(--ui-text-tertiary)',
                        children: current.stale
                          ? `${target === 'memory' ? 'MEMORY.md' : 'USER.md'} entry changed externally`
                          : `${target === 'memory' ? 'MEMORY.md' : 'USER.md'} entry ${current.index + 1}`
                      }),
                      jsx('button', {
                        type: 'button',
                        disabled: saving || draft === current.content,
                        onClick: save,
                        className: 'rounded border border-(--ui-stroke-secondary) px-2.5 py-1 text-xs hover:bg-(--chrome-action-hover) disabled:opacity-50',
                        children: saving ? 'Saving…' : 'Save changes'
                      }),
                      jsx('button', {
                        type: 'button',
                        disabled: saving || deleting || current.stale,
                        onClick: remove,
                        className: 'rounded border border-(--ui-stroke-secondary) px-2.5 py-1 text-xs hover:bg-(--chrome-action-hover) disabled:opacity-50',
                        children: deleting ? 'Deleting…' : deleteConfirm ? 'Confirm delete' : 'Delete entry'
                      })
                    ]
                  }),
                  jsx('textarea', {
                    value: draft,
                    onChange: event => {
                      setDraft(event.target.value)
                      setDeleteConfirm(false)
                    },
                    'aria-label': `Edit ${target} memory entry`,
                    className: 'min-h-0 flex-1 resize-none bg-transparent p-4 text-sm leading-relaxed outline-none',
                    spellCheck: false
                  }),
                  current.stale
                    ? jsx('div', {
                        className: 'border-t border-(--ui-stroke-secondary) px-4 py-2 text-xs text-(--ui-danger,#f87171)',
                        children: 'This entry changed on disk. Your draft is preserved; saving it will be checked against the original entry and may be rejected as stale.'
                      })
                    : null,
                  jsx('div', {
                    className: 'border-t border-(--ui-stroke-secondary) px-4 py-2 text-xs text-(--ui-text-tertiary)',
                    children: 'Saving delegates to Hermes MemoryStore validation, locking, drift detection, and atomic persistence.'
                  })
                ]
              })
              : jsx('div', {
                className: 'flex min-h-0 flex-1 items-center justify-center p-6 text-sm text-(--ui-text-tertiary)',
                children: `No ${target} entry selected.`
              })
        ]
      })
    ]
  })
}

function MemoryReviewPage(props) {
  const [mode, setMode] = useState('pending')
  return jsxs('div', {
    className: 'flex h-full min-h-0 flex-col',
    children: [
      jsx('div', {
        className: 'flex gap-1 border-b border-(--ui-stroke-secondary) px-3 py-2',
        children: [
          ['pending', 'Pending writes'],
          ['stored', 'Stored memory']
        ].map(([id, label]) =>
          jsx('button', {
            type: 'button',
            onClick: () => setMode(id),
            'aria-pressed': mode === id,
            className: `rounded px-3 py-1.5 text-xs ${
              mode === id
                ? 'bg-(--chrome-action-hover) font-medium'
                : 'text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover)'
            }`,
            children: label
          }, id)
        )
      }),
      jsx('div', {
        className: 'min-h-0 flex-1',
        children:
          mode === 'pending'
            ? jsx(PendingWritesPage, props)
            : jsx(StoredMemoryPage, {
                loadStoredMemory: props.loadStoredMemory,
                saveStoredMemory: props.saveStoredMemory,
                addStoredMemory: props.addStoredMemory,
                deleteStoredMemory: props.deleteStoredMemory,
                requestCompaction: props.requestCompaction,
                applyCompaction: props.applyCompaction,
                source: props.source
              })
      })
    ]
  })
}

export default {
  id: 'memory-review',
  name: 'Memory Review',
  description: 'Review pending Hermes memory proposals and inspect or edit stored memory.',
  defaultEnabled: false,
  register(ctx) {
    const loadRecords = () => ctx.rest('/records')
    const loadDetail = id => ctx.rest(`/records/${encodeURIComponent(id)}`)
    const loadStoredMemory = () => ctx.rest('/memory')
    const saveStoredMemory = (target, oldText, content) =>
      ctx.rest(`/memory/${encodeURIComponent(target)}`, {
        method: 'PUT',
        body: { old_text: oldText, content }
      })
    const addStoredMemory = (target, content) =>
      ctx.rest(`/memory/${encodeURIComponent(target)}/entries`, {
        method: 'POST',
        body: { content }
      })
    const deleteStoredMemory = (target, oldText) =>
      ctx.rest(`/memory/${encodeURIComponent(target)}/entries`, {
        method: 'DELETE',
        body: { old_text: oldText }
      })
    const requestCompaction = async target => {
      const parsed = await ctx.rest(`/memory/${encodeURIComponent(target)}/compact/preview`, {
        method: 'POST'
      })
      if (!parsed?.success) throw new Error(parsed?.error || 'AI compaction preview failed.')
      return parsed
    }
    const applyCompaction = (target, sourceFingerprint, entries) =>
      ctx.rest(`/memory/${encodeURIComponent(target)}/compact`, {
        method: 'POST',
        body: { source_fingerprint: sourceFingerprint, entries }
      })
    const runDecision = async (action, target) => {
      const parsed = await ctx.rest(`/records/${encodeURIComponent(target)}/decision`, {
        method: 'POST',
        body: { action }
      })
      if (!parsed?.success) throw new Error(parsed?.error || `${action} failed.`)
      return parsed
    }

    ctx.registerMany([
      {
        id: 'page',
        area: ROUTES_AREA,
        data: { path: '/memory-review' },
        render: () =>
          jsx(MemoryReviewPage, {
            loadRecords,
            loadDetail,
            loadStoredMemory,
            saveStoredMemory,
            addStoredMemory,
            deleteStoredMemory,
            requestCompaction,
            applyCompaction,
            runDecision,
            source: ctx.source
          })
      },
      {
        id: 'nav',
        area: SIDEBAR_NAV_AREA,
        order: 55,
        data: { path: '/memory-review', label: 'Memory Review', codicon: 'database' }
      }
    ])
  }
}
