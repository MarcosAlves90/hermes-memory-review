import { ROUTES_AREA, SIDEBAR_NAV_AREA, useQuery } from '@hermes/plugin-sdk'
import { useMemo, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const VIEWS = [
  ['proposal', 'Proposal'],
  ['diff', 'Diff'],
  ['raw', 'Raw'],
  ['verify', 'Verify']
]

function recordLabel(record) {
  return `${record.action}/${record.target}`
}

function MemoryReviewPage({ loadRecords, loadDetail, source }) {
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState('')
  const [view, setView] = useState('proposal')

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
                children: 'Read-only inspection of pending Hermes memory writes'
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
                    children: VIEWS.map(([id, label]) =>
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
                    )
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
                    ? jsx('pre', {
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
  description: 'Read-only inspection of pending Hermes memory proposals.',
  defaultEnabled: false,
  register(ctx) {
    const loadRecords = () => ctx.rest('/records')
    const loadDetail = id => ctx.rest(`/records/${encodeURIComponent(id)}`)

    ctx.registerMany([
      {
        id: 'page',
        area: ROUTES_AREA,
        data: { path: '/memory-review' },
        render: () => jsx(MemoryReviewPage, { loadRecords, loadDetail, source: ctx.source })
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
