import { useEffect, useState } from 'react'
import { admin, type ArchiConfig, type LLMConfig } from '../api/client'
import { Loader2, Cpu, Key, Link2, Save, RefreshCw, CheckCircle2, AlertCircle, Sparkles, FileText } from 'lucide-react'

export default function Settings() {
  const [, setConfig] = useState<LLMConfig | null>(null)
  const [, setArchiConfig] = useState<ArchiConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [savingArchi, setSavingArchi] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const [llmModel, setLlmModel] = useState('')
  const [llmFallbackModel, setLlmFallbackModel] = useState('')
  const [llmApiKey, setLlmApiKey] = useState('')
  const [llmBaseUrl, setLlmBaseUrl] = useState('')

  const [languageDetect, setLanguageDetect] = useState(true)
  const [decisionRouterLlm, setDecisionRouterLlm] = useState(false)
  const [evidenceEvaluator, setEvidenceEvaluator] = useState(false)
  const [evidenceQualityUseLlm, setEvidenceQualityUseLlm] = useState(true)
  const [selfCritic, setSelfCritic] = useState(false)
  const [finalPolish, setFinalPolish] = useState(false)
  const [docTypeClassifier, setDocTypeClassifier] = useState(false)
  const [retrievalDocTypeUseLlm, setRetrievalDocTypeUseLlm] = useState(false)
  const [llmModelEconomy, setLlmModelEconomy] = useState('gpt-4o-mini')
  const [llmTaskAwareRouting, setLlmTaskAwareRouting] = useState(true)

  const [systemPrompt, setSystemPrompt] = useState('')
  const [savingPrompt, setSavingPrompt] = useState(false)

  useEffect(() => {
    Promise.all([admin.getLLMConfig(), admin.getArchiConfig(), admin.getSystemPrompt()])
      .then(([llmData, archiData, promptData]) => {
        setConfig(llmData)
        setLlmModel(llmData.llm_model)
        setLlmFallbackModel(llmData.llm_fallback_model)
        setLlmApiKey(llmData.llm_api_key)
        setLlmBaseUrl(llmData.llm_base_url)
        setArchiConfig(archiData)
        setLanguageDetect(archiData.language_detect_enabled)
        setDecisionRouterLlm(archiData.decision_router_use_llm)
        setEvidenceEvaluator(archiData.evidence_evaluator_enabled)
        setEvidenceQualityUseLlm(archiData.evidence_quality_use_llm ?? true)
        setSelfCritic(archiData.self_critic_enabled)
        setFinalPolish(archiData.final_polish_enabled)
        setDocTypeClassifier(archiData.doc_type_classifier_enabled ?? false)
        setRetrievalDocTypeUseLlm(archiData.retrieval_doc_type_use_llm ?? false)
        setLlmModelEconomy(archiData.llm_model_economy ?? 'gpt-4o-mini')
        setLlmTaskAwareRouting(archiData.llm_task_aware_routing_enabled ?? true)
        setSystemPrompt(promptData.value)
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load config'))
      .finally(() => setLoading(false))
  }, [])

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSuccess(null)
    setSaving(true)
    try {
      await admin.updateLLMConfig({
        llm_model: llmModel.trim(),
        llm_fallback_model: llmFallbackModel.trim(),
        llm_api_key: llmApiKey,
        llm_base_url: llmBaseUrl.trim(),
      })
      setSuccess('Config saved. Cache refreshed.')
      const data = await admin.getLLMConfig()
      setConfig(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  const handleRefresh = async () => {
    setError(null)
    setSuccess(null)
    setRefreshing(true)
    try {
      await admin.refreshConfigCache()
      const [llmData, archiData, promptData] = await Promise.all([
        admin.getLLMConfig(),
        admin.getArchiConfig(),
        admin.getSystemPrompt(),
      ])
      setConfig(llmData)
      setLlmModel(llmData.llm_model)
      setLlmFallbackModel(llmData.llm_fallback_model)
      setLlmApiKey(llmData.llm_api_key)
      setLlmBaseUrl(llmData.llm_base_url)
      setArchiConfig(archiData)
      setLanguageDetect(archiData.language_detect_enabled)
      setDecisionRouterLlm(archiData.decision_router_use_llm)
      setEvidenceEvaluator(archiData.evidence_evaluator_enabled)
      setEvidenceQualityUseLlm(archiData.evidence_quality_use_llm ?? false)
      setSelfCritic(archiData.self_critic_enabled)
      setFinalPolish(archiData.final_polish_enabled)
      setDocTypeClassifier(archiData.doc_type_classifier_enabled ?? false)
      setLlmModelEconomy(archiData.llm_model_economy ?? 'gpt-4o-mini')
      setLlmTaskAwareRouting(archiData.llm_task_aware_routing_enabled ?? true)
      setSystemPrompt(promptData.value)
      setSuccess('Cache refreshed from DB.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to refresh')
    } finally {
      setRefreshing(false)
    }
  }

  const handleSaveArchi = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSuccess(null)
    setSavingArchi(true)
    try {
      await admin.updateArchiConfig({
        language_detect_enabled: languageDetect,
        decision_router_use_llm: decisionRouterLlm,
        evidence_evaluator_enabled: evidenceEvaluator,
        evidence_quality_use_llm: evidenceQualityUseLlm,
        self_critic_enabled: selfCritic,
        final_polish_enabled: finalPolish,
        doc_type_classifier_enabled: docTypeClassifier,
        retrieval_doc_type_use_llm: retrievalDocTypeUseLlm,
        llm_model_economy: llmModelEconomy.trim(),
        llm_task_aware_routing_enabled: llmTaskAwareRouting,
      })
      setSuccess('Archi v3 config saved.')
      const data = await admin.getArchiConfig()
      setArchiConfig(data)
      setLanguageDetect(data.language_detect_enabled)
      setDecisionRouterLlm(data.decision_router_use_llm)
      setEvidenceEvaluator(data.evidence_evaluator_enabled)
      setEvidenceQualityUseLlm(data.evidence_quality_use_llm ?? false)
      setSelfCritic(data.self_critic_enabled)
      setFinalPolish(data.final_polish_enabled)
      setDocTypeClassifier(data.doc_type_classifier_enabled ?? false)
      setRetrievalDocTypeUseLlm(data.retrieval_doc_type_use_llm ?? false)
      setLlmModelEconomy(data.llm_model_economy ?? 'gpt-4o-mini')
      setLlmTaskAwareRouting(data.llm_task_aware_routing_enabled ?? true)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save archi config')
    } finally {
      setSavingArchi(false)
    }
  }

  const handleSavePrompt = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSuccess(null)
    setSavingPrompt(true)
    try {
      await admin.updateSystemPrompt({ value: systemPrompt })
      setSuccess('System prompt saved. Cache refreshed.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save prompt')
    } finally {
      setSavingPrompt(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 size={28} className="animate-spin text-violet-400" />
      </div>
    )
  }

  return (
    <div className="animate-slide-up max-w-2xl space-y-8">
      <header className="mb-2 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Settings</h1>
          <p className="text-sm text-zinc-500 mt-1.5">
            LLM model, API token, and base URL. Stored in database with env fallback.
          </p>
        </div>
        <button
          type="button"
          onClick={handleRefresh}
          disabled={refreshing}
          className="flex items-center gap-2 px-4 py-2 rounded-xl input-glass text-sm text-zinc-400 hover:text-white transition-colors disabled:opacity-50"
        >
          {refreshing ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
          Refresh
        </button>
      </header>

      {(error || success) && (
        <div
          className={`flex items-center gap-3 px-4 py-3 rounded-xl ${
            error ? 'bg-red-500/10 text-red-400 border border-red-500/20' : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
          }`}
        >
          {error ? <AlertCircle size={18} /> : <CheckCircle2 size={18} />}
          <span className="text-sm">{error || success}</span>
        </div>
      )}

      <section className="glass rounded-2xl p-6">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2.5 mb-5">
          <div className="w-7 h-7 rounded-lg bg-violet-500/10 flex items-center justify-center">
            <Cpu size={15} className="text-violet-400" />
          </div>
          LLM Config
        </h2>
        <p className="text-sm text-zinc-400 mb-5">
          Model names, API key (token), and base URL. Empty URL uses OpenAI default. Values from DB override env.
        </p>
        <form onSubmit={handleSave} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-zinc-500 mb-1.5">Primary model</label>
            <input
              type="text"
              value={llmModel}
              onChange={(e) => setLlmModel(e.target.value)}
              placeholder="gpt-4o-mini"
              className="w-full px-4 py-2.5 rounded-xl input-glass text-sm"
              disabled={saving}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-500 mb-1.5">Fallback model</label>
            <input
              type="text"
              value={llmFallbackModel}
              onChange={(e) => setLlmFallbackModel(e.target.value)}
              placeholder="gpt-3.5-turbo"
              className="w-full px-4 py-2.5 rounded-xl input-glass text-sm"
              disabled={saving}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-500 mb-1.5 flex items-center gap-1.5">
              <Key size={12} />
              API key (token)
            </label>
            <input
              type="password"
              value={llmApiKey}
              onChange={(e) => setLlmApiKey(e.target.value)}
              placeholder="sk-..."
              className="w-full px-4 py-2.5 rounded-xl input-glass text-sm font-mono"
              disabled={saving}
              autoComplete="off"
            />
            <p className="text-xs text-zinc-500 mt-1">Leave empty to keep current value or use env</p>
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-500 mb-1.5 flex items-center gap-1.5">
              <Link2 size={12} />
              Base URL
            </label>
            <input
              type="url"
              value={llmBaseUrl}
              onChange={(e) => setLlmBaseUrl(e.target.value)}
              placeholder="https://api.openai.com/v1 (empty = default)"
              className="w-full px-4 py-2.5 rounded-xl input-glass text-sm font-mono"
              disabled={saving}
            />
            <p className="text-xs text-zinc-500 mt-1">Leave empty for OpenAI default.</p>
          </div>
          <button
            type="submit"
            disabled={saving}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium text-white transition-all"
            style={{
              background: 'linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%)',
            }}
          >
            {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
            Save
          </button>
        </form>
      </section>

      <section className="glass rounded-2xl p-6">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2.5 mb-5">
          <div className="w-7 h-7 rounded-lg bg-violet-500/10 flex items-center justify-center">
            <FileText size={15} className="text-violet-400" />
          </div>
          System Prompt
        </h2>
        <p className="text-sm text-zinc-400 mb-5">
          System prompt gửi tới LLM khi tạo câu trả lời. Chỉnh sửa để tùy chỉnh hành vi chatbot. Lưu trong DB, cache được refresh sau khi lưu.
        </p>
        <form onSubmit={handleSavePrompt} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-zinc-500 mb-1.5">Prompt</label>
            <textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder="You are a support assistant..."
              rows={14}
              className="w-full px-4 py-2.5 rounded-xl input-glass text-sm font-mono resize-y min-h-[200px]"
              disabled={savingPrompt}
            />
          </div>
          <button
            type="submit"
            disabled={savingPrompt || !systemPrompt.trim()}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium text-white transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            style={{
              background: 'linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%)',
            }}
          >
            {savingPrompt ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
            Save Prompt
          </button>
        </form>
      </section>

      <section className="glass rounded-2xl p-6">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2.5 mb-5">
          <div className="w-7 h-7 rounded-lg bg-violet-500/10 flex items-center justify-center">
            <Sparkles size={15} className="text-violet-400" />
          </div>
          Archi v3
        </h2>
        <p className="text-sm text-zinc-400 mb-5">
          Feature flags for language detection, evidence evaluator, self-critic, final polish, and LLM decision router. Stored in DB with env fallback.
        </p>
        <form onSubmit={handleSaveArchi} className="space-y-4">
          <ToggleRow
            label="Language detect"
            description="Detect input language (non-LLM)"
            checked={languageDetect}
            onChange={setLanguageDetect}
            disabled={savingArchi}
          />
          <ToggleRow
            label="Decision router LLM"
            description="Use LLM for gray zone decisions (hybrid)"
            checked={decisionRouterLlm}
            onChange={setDecisionRouterLlm}
            disabled={savingArchi}
          />
          <ToggleRow
            label="Evidence evaluator"
            description="LLM evaluates evidence relevance, advises Retry Planner"
            checked={evidenceEvaluator}
            onChange={setEvidenceEvaluator}
            disabled={savingArchi}
          />
          <ToggleRow
            label="Evidence quality (LLM)"
            description="Use LLM for evidence quality gate instead of regex"
            checked={evidenceQualityUseLlm}
            onChange={setEvidenceQualityUseLlm}
            disabled={savingArchi}
          />
          <ToggleRow
            label="Self-critic"
            description="Regenerate answer on self-critic fail"
            checked={selfCritic}
            onChange={setSelfCritic}
            disabled={savingArchi}
          />
          <ToggleRow
            label="Final polish"
            description="LLM polish for clarity, structure, tone"
            checked={finalPolish}
            onChange={setFinalPolish}
            disabled={savingArchi}
          />
          <ToggleRow
            label="Doc type classifier"
            description="Use LLM to classify crawled docs (policy, tos, faq, howto, pricing) from content instead of URL"
            checked={docTypeClassifier}
            onChange={setDocTypeClassifier}
            disabled={savingArchi}
          />
          <ToggleRow
            label="Retrieval doc type (LLM)"
            description="Use LLM to select which doc types to search based on query semantics (policy, faq, pricing, etc.)"
            checked={retrievalDocTypeUseLlm}
            onChange={setRetrievalDocTypeUseLlm}
            disabled={savingArchi}
          />
          <div className="pt-2 border-t border-white/[0.06] mt-2">
            <div className="text-sm font-medium text-zinc-300 mb-2">Model routing</div>
            <div className="space-y-3">
              <ToggleRow
                label="Task-aware routing"
                description="Primary (gpt-5.2) for generate/self_critic, economy for normalizer/decision_router/etc."
                checked={llmTaskAwareRouting}
                onChange={setLlmTaskAwareRouting}
                disabled={savingArchi}
              />
              <div>
                <label className="block text-xs font-medium text-zinc-500 mb-1.5">Economy model</label>
                <input
                  type="text"
                  value={llmModelEconomy}
                  onChange={(e) => setLlmModelEconomy(e.target.value)}
                  placeholder="gpt-4o-mini"
                  className="w-full px-4 py-2.5 rounded-xl input-glass text-sm"
                  disabled={savingArchi}
                />
                <p className="text-xs text-zinc-500 mt-1">Used for normalizer, decision_router, evidence_evaluator, evidence_quality, final_polish</p>
              </div>
            </div>
          </div>
          <button
            type="submit"
            disabled={savingArchi}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium text-white transition-all"
            style={{
              background: 'linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%)',
            }}
          >
            {savingArchi ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
            Save Archi
          </button>
        </form>
      </section>
    </div>
  )
}

function ToggleRow({
  label,
  description,
  checked,
  onChange,
  disabled,
}: {
  label: string
  description: string
  checked: boolean
  onChange: (v: boolean) => void
  disabled?: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <div>
        <div className="text-sm font-medium text-white">{label}</div>
        <div className="text-xs text-zinc-500 mt-0.5">{description}</div>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked ? 'true' : 'false'}
        aria-label={`${label}: ${checked ? 'on' : 'off'}`}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`
          relative w-11 h-6 rounded-full transition-colors shrink-0
          ${checked ? 'bg-violet-500' : 'bg-zinc-600'}
          ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
        `}
      >
        <span
          className={`
            absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-transform
            ${checked ? 'translate-x-5' : 'translate-x-0'}
          `}
        />
      </button>
    </div>
  )
}
