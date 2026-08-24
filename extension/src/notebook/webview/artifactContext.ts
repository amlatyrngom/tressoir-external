export type TressoirArtifactContext = Readonly<{
  feedbackKey: string
  interactionsFile: string
}>

const DEFAULT_FEEDBACK_KEY = 'free_form_feedback'
const DEFAULT_INTERACTIONS_FILE = 'interactions.json'

export function createArtifactContext(dataset: DOMStringMap): TressoirArtifactContext {
  return Object.freeze({
    feedbackKey: dataset.feedbackKey || DEFAULT_FEEDBACK_KEY,
    interactionsFile: dataset.interactionsFile || DEFAULT_INTERACTIONS_FILE,
  })
}
