// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { createArtifactContext } from '../notebook/webview/artifactContext'

describe('raw HTML artifact context', () => {
  it('exposes the provider-generated feedback identity and interaction filename read-only', () => {
    document.body.dataset.feedbackKey = 'acceptance-free_form_feedback'
    document.body.dataset.interactionsFile = 'interactions.acceptance.json'

    const context = createArtifactContext(document.body.dataset)

    expect(context).toEqual({
      feedbackKey: 'acceptance-free_form_feedback',
      interactionsFile: 'interactions.acceptance.json',
    })
    expect(Object.isFrozen(context)).toBe(true)
  })

  it('has safe browser-test fallbacks when provider data is absent', () => {
    delete document.body.dataset.feedbackKey
    delete document.body.dataset.interactionsFile

    expect(createArtifactContext(document.body.dataset)).toEqual({
      feedbackKey: 'free_form_feedback',
      interactionsFile: 'interactions.json',
    })
  })
})
