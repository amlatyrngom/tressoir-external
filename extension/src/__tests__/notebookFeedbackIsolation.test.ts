// @vitest-environment node
import { afterEach, describe, expect, it } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import { JSDOM } from 'jsdom'

// Exercise the shipped classic runtime in separate webview-like realms. This catches regressions
// where provider HTML still carries a source name but the actual feedback widget reads or writes
// the old shared key.
const runtimeSource = readFileSync(
  resolve(__dirname, '../notebook/assets/tressoir-md.js'),
  'utf8',
)

type Call = ['get', string] | ['store', string, string]

function feedbackRealm(
  sourceName: string,
  stored: Record<string, unknown>,
  feedbackKey = `${sourceName}-free_form_feedback`,
) {
  const dom = new JSDOM(
    '<!doctype html><html><body><textarea id="ff-editor"></textarea></body></html>',
    { runScripts: 'outside-only', url: 'https://artifact.test/' },
  )
  dom.window.document.body.dataset.sourceName = sourceName
  dom.window.document.body.dataset.feedbackKey = feedbackKey
  const calls: Call[] = []
  const handlers: Record<string, () => void> = {}
  let value = ''

  ;(dom.window as any).CodeMirror = {
    fromTextArea(textarea: HTMLTextAreaElement) {
      value = textarea.value
      return {
        getValue: () => value,
        on: (name: string, handler: () => void) => {
          handlers[name] = handler
        },
      }
    },
  }
  ;(dom.window as any).tressoirNotebook = {
    getInteraction(key: string) {
      calls.push(['get', key])
      return stored[key]
    },
    storeInteraction(key: string, nextValue: string) {
      calls.push(['store', key, nextValue])
    },
  }

  dom.window.eval(runtimeSource)
  dom.window.document.dispatchEvent(new dom.window.CustomEvent('tressoir:render'))

  return {
    dom,
    calls,
    value: () => value,
    save(nextValue: string) {
      value = nextValue
      handlers.blur()
    },
  }
}

const realms: JSDOM[] = []
afterEach(() => {
  while (realms.length > 0) realms.pop()?.window.close()
})

describe('free-form feedback runtime isolation', () => {
  it('restores and persists different keys for sibling Markdown artifacts', () => {
    const plan = feedbackRealm('PLAN', {
      free_form_feedback: 'ambiguous legacy text',
      'PLAN-free_form_feedback': 'plan text',
      'RESEARCH-free_form_feedback': 'wrong sibling text',
    })
    const research = feedbackRealm('RESEARCH', {
      free_form_feedback: 'ambiguous legacy text',
      'PLAN-free_form_feedback': 'wrong sibling text',
      'RESEARCH-free_form_feedback': 'research text',
    })
    const fresh = feedbackRealm('NEW', {
      free_form_feedback: 'ambiguous legacy text',
    })
    realms.push(plan.dom, research.dom, fresh.dom)

    expect(plan.value()).toBe('plan text')
    expect(research.value()).toBe('research text')
    expect(fresh.value()).toBe('')
    expect(plan.calls).toEqual([['get', 'PLAN-free_form_feedback']])
    expect(research.calls).toEqual([['get', 'RESEARCH-free_form_feedback']])
    expect(fresh.calls).toEqual([['get', 'NEW-free_form_feedback']])

    plan.save('updated plan')
    research.save('updated research')

    expect(plan.calls.at(-1)).toEqual(['store', 'PLAN-free_form_feedback', 'updated plan'])
    expect(research.calls.at(-1)).toEqual([
      'store',
      'RESEARCH-free_form_feedback',
      'updated research',
    ])
    expect(plan.calls.some((call) => call[1] === 'free_form_feedback')).toBe(false)
    expect(research.calls.some((call) => call[1] === 'free_form_feedback')).toBe(false)
  })

  it('uses the complete provider key without browser entity normalization', () => {
    const entityName = feedbackRealm(
      'A&amp;B',
      {
        'A&amp;B-free_form_feedback': 'entity spelling',
        'A&B-free_form_feedback': 'literal ampersand',
      },
      'A&amp;B-free_form_feedback',
    )
    const literalName = feedbackRealm(
      'A&B',
      {
        'A&amp;B-free_form_feedback': 'entity spelling',
        'A&B-free_form_feedback': 'literal ampersand',
      },
      'A&B-free_form_feedback',
    )
    realms.push(entityName.dom, literalName.dom)

    expect(entityName.value()).toBe('entity spelling')
    expect(literalName.value()).toBe('literal ampersand')
    expect(entityName.calls[0]).toEqual(['get', 'A&amp;B-free_form_feedback'])
    expect(literalName.calls[0]).toEqual(['get', 'A&B-free_form_feedback'])
  })
})
