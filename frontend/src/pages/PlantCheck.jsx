import { useEffect, useRef, useState } from 'react';
import { AlertCircle, CheckCircle2, ImagePlus, LoaderCircle, ScanSearch, Save, X } from 'lucide-react';
import api from '../services/api';
import { getCurrentUserId } from '../utils/storage';

const INITIAL = { plant_name: '', plant_type: '', location: '', symptoms: '' };
const CATEGORIES = ['fruit', 'vegetable', 'flowering', 'herb', 'tree', 'indoor', 'succulent', 'climber', 'palm', 'fern', 'grass', 'crop', 'aquatic', 'other'];
const ALLOWED = ['image/jpeg', 'image/png', 'image/webp'];
const MAX_SIZE = 5 * 1024 * 1024;

function errorText(error, fallback) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg || '').filter(Boolean).join(' ');
  return error?.message || fallback;
}

function formDataFor(values, file) {
  const data = new FormData();
  data.append('plant_name', values.plant_name.trim());
  data.append('plant_type', values.plant_type);
  data.append('symptoms', values.symptoms.trim());
  if (values.location.trim()) data.append('location', values.location.trim());
  if (file) data.append('image', file);
  return data;
}

function ValidationDetails({ validation }) {
  if (!validation) return null;
  const plant = validation.plant_match;
  const category = validation.category_match;
  return (
    <div className="result" style={{ marginTop: 16 }}>
      <h3>Plant Verification</h3>
      <p><strong>Plant / Image Match:</strong> {plant?.status || 'UNKNOWN'}</p>
      {plant?.reason && <p>{plant.reason}</p>}
      {plant?.correction_instruction && <p className="notice error-box">{plant.correction_instruction}</p>}
      <p><strong>Category Match:</strong> {category?.status || 'UNKNOWN'}</p>
      {category?.reason && <p>{category.reason}</p>}
      {category?.suggested_categories?.length > 0 && (
        <p>Suggested categories: {category.suggested_categories.join(', ')}</p>
      )}
      {validation.image_is_plant === false && <p className="notice error-box">The uploaded image does not appear to show a plant.</p>}
      {validation.image_is_clear_enough === false && <p className="notice error-box">Please upload a clearer plant image.</p>}
      {!validation.can_continue && <p className="notice error-box" role="alert"><AlertCircle size={18} /> Diagnosis stopped because the submitted information did not pass validation. Correct the form and start again.</p>}
    </div>
  );
}

export default function PlantCheck() {
  const [form, setForm] = useState(INITIAL);
  const [errors, setErrors] = useState({});
  const [image, setImage] = useState(null);
  const [preview, setPreview] = useState(null);
  const [interview, setInterview] = useState(null);
  const [answers, setAnswers] = useState({});
  const [validation, setValidation] = useState(null);
  const [result, setResult] = useState(null);
  const [analyzedForm, setAnalyzedForm] = useState(null);
  const [analyzedImageName, setAnalyzedImageName] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [apiError, setApiError] = useState('');
  const [retrySeconds, setRetrySeconds] = useState(0);
  const requestInFlight = useRef(false);
  const saveInFlight = useRef(false);
  const fileInputRef = useRef(null);
  const formVersion = useRef(0);

  useEffect(() => {
    if (retrySeconds <= 0) return undefined;
    const timer = setTimeout(() => setRetrySeconds((n) => Math.max(0, n - 1)), 1000);
    return () => clearTimeout(timer);
  }, [retrySeconds]);

  useEffect(() => {
    if (!image) { setPreview(null); return undefined; }
    const url = URL.createObjectURL(image);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [image]);

  const resetDiagnosis = () => {
    formVersion.current += 1;
    setInterview(null);
    setAnswers({});
    setValidation(null);
    setResult(null);
    setAnalyzedForm(null);
    setAnalyzedImageName('');
    setSaved(false);
    setApiError('');
  };

  const updateField = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => ({ ...prev, [key]: '' }));
    resetDiagnosis();
  };

  const selectImage = (event) => {
    const file = event.target.files?.[0] || null;
    resetDiagnosis();
    setErrors((prev) => ({ ...prev, image: '' }));
    if (!file) { setImage(null); return; }
    let message = '';
    if (!ALLOWED.includes(file.type)) message = 'Only JPG, PNG and WebP images are allowed.';
    else if (file.size === 0) message = 'The selected image is empty.';
    else if (file.size > MAX_SIZE) message = 'Image size must not exceed 5 MB.';
    if (message) {
      setImage(null);
      setErrors((prev) => ({ ...prev, image: message }));
      event.target.value = '';
      return;
    }
    setImage(file);
  };

  const removeImage = () => {
    setImage(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
    setErrors((prev) => ({ ...prev, image: '' }));
    resetDiagnosis();
  };

  const validate = () => {
    const next = {};
    if (!form.plant_name.trim()) next.plant_name = 'Plant name is required.';
    if (!CATEGORIES.includes(form.plant_type)) next.plant_type = 'Choose a valid plant category.';
    if (!form.symptoms.trim()) next.symptoms = 'Describe the symptoms you see.';
    if (image && (!ALLOWED.includes(image.type) || !image.size || image.size > MAX_SIZE)) next.image = 'Choose a valid image under 5 MB.';
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const handleRequestError = (err) => {
    if (err?.response?.status === 429) setRetrySeconds(30);
    setApiError(errorText(err, 'Unable to contact the diagnosis service. Please try again.'));
  };

  const start = async (event) => {
    event.preventDefault();
    if (requestInFlight.current || saveInFlight.current || retrySeconds > 0) return;
    if (!validate()) { setApiError('INVALID INPUT — Please review the highlighted fields.'); return; }
    requestInFlight.current = true;
    setLoading(true);
    setApiError('');
    setInterview(null);
    setAnswers({});
    setValidation(null);
    setResult(null);
    setSaved(false);
    const version = formVersion.current;
    try {
      const response = await api.post('/api/diagnosis/start', formDataFor(form, image));
      if (version !== formVersion.current) return;
      const data = response.data;
      if (!data?.validation || !Array.isArray(data.questions)) throw new Error('Invalid interview response from the server.');
      setValidation(data.validation);
      if (data.validation.can_continue) {
        if (!data.interview_token || data.questions.length < 3 || data.questions.length > 5) throw new Error('Incomplete interview response from the server.');
        setInterview({ token: data.interview_token, questions: data.questions, originalForm: { ...form }, originalImage: image });
      }
    } catch (err) {
      if (version === formVersion.current) handleRequestError(err);
    } finally {
      requestInFlight.current = false;
      setLoading(false);
    }
  };

  const complete = async (event) => {
    event.preventDefault();
    if (!interview || requestInFlight.current || retrySeconds > 0) return;
    const unanswered = interview.questions.filter((q) => !answers[q.id]?.trim());
    if (unanswered.length) { setApiError('Please answer every question or select Not sure.'); return; }
    requestInFlight.current = true;
    setLoading(true);
    setApiError('');
    const version = formVersion.current;
    try {
      const payload = formDataFor(interview.originalForm, interview.originalImage);
      payload.append('interview_token', interview.token);
      payload.append('answers_json', JSON.stringify(interview.questions.map((q) => ({
        question_id: q.id, question: q.question, answer: answers[q.id].trim(),
      }))));
      const response = await api.post('/api/diagnosis/complete', payload);
      if (version !== formVersion.current) return;
      const data = response.data;
      if (!data || typeof data.possible_issue !== 'string' || typeof data.explanation !== 'string' ||
          !Array.isArray(data.care_suggestions) || data.care_suggestions.length !== 3 ||
          typeof data.expert_advice !== 'string') throw new Error('Invalid final diagnosis returned by the server.');
      setResult(data);
      setValidation(data.validation || validation);
      setAnalyzedForm({ ...interview.originalForm });
      setAnalyzedImageName(interview.originalImage?.name || '');
      setInterview(null);
    } catch (err) {
      if (version === formVersion.current) handleRequestError(err);
    } finally {
      requestInFlight.current = false;
      setLoading(false);
    }
  };

  const save = async () => {
    if (!result || !analyzedForm || saving || saved || saveInFlight.current || requestInFlight.current) return;
    const userId = getCurrentUserId();
    if (!userId) { setApiError('Please save your name and email on the People page before saving a plant.'); return; }
    saveInFlight.current = true;
    setSaving(true);
    setApiError('');
    const version = formVersion.current;
    try {
      await api.post('/api/plants', {
        user_id: userId,
        plant_name: analyzedForm.plant_name,
        plant_type: analyzedForm.plant_type,
        location: analyzedForm.location || null,
        symptom: analyzedForm.symptoms,
        analysis: {
          possible_issue: result.possible_issue,
          explanation: result.explanation,
          care_suggestions: result.care_suggestions,
          expert_advice: result.expert_advice,
          expert_advice_needed: result.expert_advice_needed,
          ai_confidence: result.ai_confidence ?? null,
          plant_match: result.plant_match ?? null,
          category_match: result.category_match ?? null,
          interview_answers: result.interview_answers ?? null,
        },
      });
      if (version === formVersion.current) setSaved(true);
    } catch (err) {
      if (version === formVersion.current) handleRequestError(err);
    } finally {
      saveInFlight.current = false;
      setSaving(false);
    }
  };

  const busy = loading || saving;
  return (
    <section>
      <div className="page-heading">
        <p className="eyebrow">PLANT CARE TOOL</p>
        <h1>Plant Check</h1>
        <p>Enter plant details, optionally upload a clear image, and answer AI follow-up questions for personalized plant care guidance.</p>
      </div>
      <div className="two-cards analysis-grid">
        <article className="card">
          <h2>Plant analysis form</h2>
          <form onSubmit={start} noValidate>
            <label>Plant Name
              <input value={form.plant_name} onChange={(e) => updateField('plant_name', e.target.value)} disabled={busy} aria-invalid={!!errors.plant_name} placeholder="e.g. Tomato" />
              {errors.plant_name && <span className="error">{errors.plant_name}</span>}
            </label>
            <label>Plant Type / Category
              <select value={form.plant_type} onChange={(e) => updateField('plant_type', e.target.value)} disabled={busy} aria-invalid={!!errors.plant_type}>
                <option value="">Select a plant category</option>
                {CATEGORIES.map((category) => <option key={category} value={category}>{category.charAt(0).toUpperCase() + category.slice(1)}</option>)}
              </select>
              {errors.plant_type && <span className="error">{errors.plant_type}</span>}
            </label>
            <label>Location (optional)
              <input value={form.location} onChange={(e) => updateField('location', e.target.value)} disabled={busy} placeholder="e.g. Home garden" />
            </label>
            <label>Symptoms
              <textarea value={form.symptoms} onChange={(e) => updateField('symptoms', e.target.value)} disabled={busy} aria-invalid={!!errors.symptoms} placeholder="For example: yellow leaves, brown spots..." />
              {errors.symptoms && <span className="error">{errors.symptoms}</span>}
            </label>
            <div className="form-field">
              <label htmlFor="plantImage">Plant / Leaf Image (optional)</label>
              <div style={{ border: '1px dashed #8cae91', borderRadius: 12, padding: 16, marginTop: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}><ImagePlus size={22} /><span>Upload a clear plant image</span></div>
                <input ref={fileInputRef} id="plantImage" type="file" accept="image/jpeg,image/png,image/webp" onChange={selectImage} disabled={busy} aria-invalid={!!errors.image} />
                <p style={{ fontSize: 12, marginTop: 8, opacity: 0.75 }}>JPG, PNG or WebP. Maximum 5 MB.</p>
                {errors.image && <p className="error" role="alert">{errors.image}</p>}
                {preview && <div style={{ marginTop: 12, position: 'relative', maxWidth: 260 }}>
                  <img src={preview} alt="Selected plant preview" style={{ display: 'block', width: '100%', maxHeight: 220, objectFit: 'contain', borderRadius: 10 }} />
                  <button type="button" onClick={removeImage} disabled={busy} aria-label="Remove selected image" style={{ position: 'absolute', top: 8, right: 8, border: 'none', borderRadius: '50%', padding: 6, cursor: 'pointer', background: '#fff', color: '#222' }}><X size={16} /></button>
                  <p style={{ fontSize: 12, marginTop: 6, overflowWrap: 'anywhere' }}>{image?.name}</p>
                </div>}
              </div>
            </div>
            <button className="button" type="submit" disabled={busy || retrySeconds > 0 || !!errors.image}>
              {loading ? <><LoaderCircle className="spin" size={18} /> Checking...</> : retrySeconds > 0 ? `Try again in ${retrySeconds}s` : <><ScanSearch size={18} /> Start Smart Diagnosis</>}
            </button>
          </form>
          {apiError && <p className="notice error-box" role="alert"><AlertCircle size={18} /> {apiError}</p>}
        </article>
        <article className="card result-card">
          <h2>Plant health analysis</h2>
          {!result && !interview && !validation && !loading && <div className="empty"><ScanSearch size={42} /><p>Submit plant details to verify your plant and begin a smart diagnostic interview.</p></div>}
          {loading && <div className="empty"><LoaderCircle className="spin" size={42} /><p>Processing your plant check...</p></div>}
          {!loading && <ValidationDetails validation={validation} />}
          {!loading && interview && <form onSubmit={complete} className="result" style={{ marginTop: 20 }}>
            <h3>Smart Diagnostic Interview</h3>
            <p>Answer all {interview.questions.length} questions. You can select “Not sure” when you do not know.</p>
            {interview.questions.map((q, index) => <div key={q.id} style={{ marginBottom: 18 }}>
              <label htmlFor={`interview-${q.id}`}>{index + 1}. {q.question}</label>
              {q.explanation && <p style={{ fontSize: 13, opacity: 0.8 }}>{q.explanation}</p>}
              <textarea id={`interview-${q.id}`} value={answers[q.id] || ''} onChange={(e) => { setAnswers((prev) => ({ ...prev, [q.id]: e.target.value })); setApiError(''); }} placeholder="Type your answer or select Not sure" disabled={busy} maxLength={1000} />
              <button type="button" onClick={() => setAnswers((prev) => ({ ...prev, [q.id]: 'Not sure' }))} disabled={busy} style={{ marginTop: 6 }}>Not sure</button>
            </div>)}
            <button className="button" type="submit" disabled={busy || retrySeconds > 0}><ScanSearch size={18} /> Complete Diagnosis</button>
          </form>}
          {!loading && result && <div className="result">
            <span className="demo-label">{result.demo === false ? 'AI-GENERATED GUIDANCE — NOT A CONFIRMED DIAGNOSIS' : 'DEMO GUIDANCE — NOT AN AI DIAGNOSIS'}</span>
            {analyzedImageName && <p><CheckCircle2 size={16} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 6 }} /> Image analyzed: {analyzedImageName}</p>}
            {typeof result.ai_confidence === 'number' && <p><strong>AI Self-Estimated Confidence:</strong> {result.ai_confidence}% <small>(not a calibrated probability)</small></p>}
            <h4>Possible Issue</h4><h3>{result.possible_issue}</h3>
            <h4>Explanation</h4><p>{result.explanation}</p>
            <h4>Care Suggestions</h4><ul>{result.care_suggestions.map((suggestion, index) => <li key={`${index}-${suggestion}`}>{suggestion}</li>)}</ul>
            <h4>Expert Advice</h4>
            {result.expert_advice_needed && <p className="notice error-box"><AlertCircle size={18} /> Expert agricultural advice is recommended.</p>}
            <p>{result.expert_advice}</p>
            <p className="disclaimer">This analysis is general guidance, not a confirmed plant disease diagnosis.</p>
            <button className="button" type="button" onClick={save} disabled={busy || saved}>
              {saving ? <><LoaderCircle className="spin" size={18} /> Saving...</> : saved ? <><CheckCircle2 size={18} /> Saved to My Plants</> : <><Save size={18} /> Save to My Plants</>}
            </button>
            {saved && analyzedImageName && <p className="disclaimer" style={{ marginTop: 10 }}>Analysis saved successfully. The uploaded image itself is not stored with the plant record.</p>}
          </div>}
        </article>
      </div>
    </section>
  );
}
