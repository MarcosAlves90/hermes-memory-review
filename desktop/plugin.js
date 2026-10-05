import { ROUTES_AREA, SIDEBAR_NAV_AREA, host, useQuery } from '@hermes/plugin-sdk'
import { useMemo, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const VIEWS = [
  ['overview', 'Overview'],
  ['proposal', 'Proposal'],
  ['diff', 'Diff'],
  ['raw', 'Raw'],
  ['verify', 'Verify']
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

function MemoryReviewPage({ loadRecords, loadDetail, runDecision, source }) {
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
            children: `${listing.data?.count ?? 0} pending`
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
                  disabled: Boolean(busyAction),
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
                  disabled: Boolean(busyAction),
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
                        disabled: Boolean(busyAction),
                        onClick: () => decide('approve', currentId),
                        className: 'rounded border border-(--ui-stroke-secondary) px-2.5 py-1 text-xs hover:bg-(--chrome-action-hover) disabled:opacity-50',
                        children: busyAction === `approve:${currentId}` ? 'Approving…' : 'Approve'
                      }, 'approve'),
                      jsx('button', {
                        type: 'button',
                        disabled: Boolean(busyAction),
                        onClick: () => decide('reject', currentId),
                        className: 'rounded border border-(--ui-stroke-secondary) px-2.5 py-1 text-xs text-(--ui-danger,#f87171) hover:bg-(--chrome-action-hover) disabled:opacity-50',
                        children: busyAction === `reject:${currentId}` ? 'Rejecting…' : 'Reject'
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

export default {
  id: 'memory-review',
  name: 'Memory Review',
  description: 'Review, approve, or reject pending Hermes memory proposals.',
  defaultEnabled: false,
  register(ctx) {
    const loadRecords = () => ctx.rest('/records')
    const loadDetail = id => ctx.rest(`/records/${encodeURIComponent(id)}`)
    const runDecision = async (action, target) => {
      const activeSessionId = host.state.activeSessionId.get()
      const focusedSessionId = host.state.focusedSessionId.get()
      const sessionId = focusedSessionId || activeSessionId
      if (!sessionId) {
        throw new Error('Open or focus a Hermes session before approving or rejecting memory.')
      }
      return host.request('slash.exec', {
        session_id: sessionId,
        command: `/memory ${action} ${target}`
      })
    }

    ctx.registerMany([
      {
        id: 'page',
        area: ROUTES_AREA,
        data: { path: '/memory-review' },
        render: () => jsx(MemoryReviewPage, { loadRecords, loadDetail, runDecision, source: ctx.source })
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
