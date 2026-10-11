
import { useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  ImagePlus,
  LoaderCircle,
  ScanSearch,
  Save,
  X,
} from 'lucide-react';

import api from '../services/api';
import { getCurrentUserId } from '../utils/storage';

const initial = {
  plant_name: '',
  plant_type: '',
  location: '',
  symptoms: '',
};

const MAX_IMAGE_SIZE = 5 * 1024 * 1024;

const ALLOWED_IMAGE_TYPES = [
  'image/jpeg',
  'image/png',
  'image/webp',
];

const invalidInputMessage = (detail) => {
  if (!Array.isArray(detail)) {
    return typeof detail === 'string'
      ? detail
      : 'INVALID INPUT — Please review the form and try again.';
  }

  const messages = detail
    .map((issue) =>
      typeof issue.msg === 'string'
        ? issue.msg.replace(/^Value error,\s*/, '')
        : ''
    )
    .filter(Boolean);

  return `INVALID INPUT — ${
    messages.join(' ') || 'Please review the form and try again.'
  }`;
};

const getErrorMessage = (err, fallback) => {
  const detail = err.response?.data?.detail;

  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }

  if (Array.isArray(detail)) {
    return invalidInputMessage(detail);
  }

  return fallback;
};

const isValidAnalysis = (data) => (
  data !== null &&
  typeof data === 'object' &&
  !Array.isArray(data) &&
  typeof data.possible_issue === 'string' &&
  typeof data.explanation === 'string' &&
  typeof data.expert_advice === 'string' &&
  typeof data.expert_advice_needed === 'boolean' &&
  Array.isArray(data.care_suggestions) &&
  data.care_suggestions.length === 3 &&
  data.care_suggestions.every(
    (item) => typeof item === 'string' && Boolean(item.trim())
  )
);

export default function PlantCheck() {
  const [form, setForm] = useState(initial);
  const [errors, setErrors] = useState({});

  const [image, setImage] = useState(null);
  const [preview, setPreview] = useState(null);

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

    const timer = setTimeout(() => {
      setRetrySeconds((seconds) => Math.max(0, seconds - 1));
    }, 1000);

    return () => clearTimeout(timer);
  }, [retrySeconds]);

  // Create and clean up the image preview URL.
  useEffect(() => {
    if (!image) {
      setPreview(null);
      return undefined;
    }

    const objectUrl = URL.createObjectURL(image);
    setPreview(objectUrl);

    return () => {
      URL.revokeObjectURL(objectUrl);
    };
  }, [image]);

  const clearAnalysis = () => {
    formVersion.current += 1;
    setResult(null);
    setAnalyzedForm(null);
    setAnalyzedImageName('');
    setSaved(false);
    setApiError('');
  };

  const updateField = (key, value) => {
    setForm((previous) => ({
      ...previous,
      [key]: value,
    }));

    setErrors((previous) => ({
      ...previous,
      [key]: '',
    }));

    clearAnalysis();
  };

  const selectImage = (event) => {
    const file = event.target.files?.[0];

    clearAnalysis();
    setErrors((previous) => ({
      ...previous,
      image: '',
    }));

    if (!file) {
      setImage(null);
      return;
    }

    if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
      setImage(null);
      setErrors((previous) => ({
        ...previous,
        image: 'Only JPG, PNG and WebP images are allowed.',
      }));
      event.target.value = '';
      return;
    }

    if (file.size === 0) {
      setImage(null);
      setErrors((previous) => ({
        ...previous,
        image: 'The selected image is empty.',
      }));
      event.target.value = '';
      return;
    }

    if (file.size > MAX_IMAGE_SIZE) {
      setImage(null);
      setErrors((previous) => ({
        ...previous,
        image: 'Image size must not exceed 5 MB.',
      }));
      event.target.value = '';
      return;
    }

    setImage(file);
  };

  const removeImage = () => {
    setImage(null);

    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }

    setErrors((previous) => ({
      ...previous,
      image: '',
    }));

    clearAnalysis();
  };

  const validate = () => {
    const nextErrors = {};

    if (!form.plant_name.trim()) {
      nextErrors.plant_name = 'Plant name is required.';
    }

    if (!form.plant_type.trim()) {
      nextErrors.plant_type = 'Plant type is required.';
    }

    if (!form.symptoms.trim()) {
      nextErrors.symptoms = 'Describe the symptoms you see.';
    }

    if (image && !ALLOWED_IMAGE_TYPES.includes(image.type)) {
      nextErrors.image = 'Unsupported image format.';
    }

    if (image && image.size > MAX_IMAGE_SIZE) {
      nextErrors.image = 'Image size must not exceed 5 MB.';
    }

    if (image && image.size === 0) {
      nextErrors.image = 'The selected image is empty.';
    }

    setErrors(nextErrors);

    return Object.keys(nextErrors).length === 0;
  };

  const submit = async (event) => {
    event.preventDefault();

    if (requestInFlight.current || saveInFlight.current) {
      return;
    }

    if (retrySeconds > 0) {
      setApiError(
        `AI analysis is busy. Please try again in ${retrySeconds} seconds.`
      );
      return;
    }

    if (!validate()) {
      setApiError(
        'INVALID INPUT — Please review the highlighted fields.'
      );
      return;
    }

    requestInFlight.current = true;
    setLoading(true);
    setApiError('');
    setResult(null);
    setAnalyzedForm(null);
    setAnalyzedImageName('');
    setSaved(false);

    const submittedForm = { ...form };
    const submittedImage = image;
    const submittedVersion = formVersion.current;

    try {
      let response;

      if (submittedImage) {
        const formData = new FormData();

        formData.append(
          'plant_name',
          submittedForm.plant_name.trim()
        );
        formData.append(
          'plant_type',
          submittedForm.plant_type.trim()
        );
        formData.append(
          'symptoms',
          submittedForm.symptoms.trim()
        );

        if (submittedForm.location.trim()) {
          formData.append(
            'location',
            submittedForm.location.trim()
          );
        }

        formData.append('image', submittedImage);

        // Do not manually set multipart Content-Type.
        response = await api.post(
          '/api/analyze-image',
          formData
        );
      } else {
        response = await api.post(
          '/api/analyze',
          submittedForm
        );
      }

      // Ignore an old response if the user changed the form
      // or image while the request was in progress.
      if (submittedVersion !== formVersion.current) {
        return;
      }

      if (!isValidAnalysis(response.data)) {
        throw new Error(
          'The AI returned an invalid structured response.'
        );
      }

      setResult(response.data);
      setAnalyzedForm(submittedForm);
      setAnalyzedImageName(submittedImage?.name || '');
    } catch (err) {
      if (submittedVersion !== formVersion.current) {
        return;
      }

      const status = err.response?.status;

      if (status === 422) {
        setApiError(
          invalidInputMessage(err.response?.data?.detail)
        );
      } else if (status === 429) {
        setRetrySeconds(30);
        setApiError(
          'AI analysis is busy. Please wait 30 seconds before trying again.'
        );
      } else if (status === 413) {
        setApiError(
          'Image size must not exceed 5 MB.'
        );
      } else if (status === 400) {
        setApiError(
          getErrorMessage(
            err,
            'Please upload a valid JPG, PNG or WebP image.'
          )
        );
      } else {
        setApiError(
          getErrorMessage(
            err,
            err.message ===
              'The AI returned an invalid structured response.'
              ? err.message
              : 'Unable to reach the analysis service. Please try again.'
          )
        );
      }
    } finally {
      requestInFlight.current = false;
      setLoading(false);
    }
  };

  const save = async () => {
    if (
      !result ||
      !analyzedForm ||
      saving ||
      saved ||
      saveInFlight.current ||
      requestInFlight.current
    ) {
      return;
    }

    const userId = getCurrentUserId();

    if (!userId) {
      setApiError(
        'Please save your name and email on the People page before saving a plant.'
      );
      return;
    }

    saveInFlight.current = true;
    setSaving(true);
    setApiError('');

    try {
      // Existing API saves structured analysis as before.
      // Image persistence requires a separate backend update.
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
        },
      });

      setSaved(true);
    } catch (err) {
      setSaved(false);
      setApiError(
        getErrorMessage(
          err,
          'Unable to save this plant. Please try again.'
        )
      );
    } finally {
      saveInFlight.current = false;
      setSaving(false);
    }
  };

  const guidanceLabel = result?.demo === false
    ? 'AI-GENERATED GUIDANCE — NOT A CONFIRMED DIAGNOSIS'
    : 'DEMO GUIDANCE — NOT AN AI DIAGNOSIS';

  return (
    <section>
      <div className="page-heading">
        <p className="eyebrow">PLANT CARE TOOL</p>
        <h1>Plant Check</h1>
        <p>
          Enter your plant details and optionally upload a
          leaf or plant image for AI-powered guidance.
        </p>
      </div>

      <div className="two-cards analysis-grid">
        <article className="card">
          <h2>Plant analysis form</h2>

          <form onSubmit={submit} noValidate>
            {[
              ['plant_name', 'Plant Name'],
              ['plant_type', 'Plant Type'],
              ['location', 'Location (optional)'],
            ].map(([key, label]) => (
              <label key={key}>
                {label}

                <input
                  value={form[key]}
                  onChange={(event) => {
                    updateField(key, event.target.value);
                  }}
                  disabled={loading || saving}
                  aria-invalid={!!errors[key]}
                />

                {errors[key] && (
                  <span className="error">
                    {errors[key]}
                  </span>
                )}
              </label>
            ))}

            <label>
              Symptoms

              <textarea
                value={form.symptoms}
                onChange={(event) => {
                  updateField(
                    'symptoms',
                    event.target.value
                  );
                }}
                disabled={loading || saving}
                aria-invalid={!!errors.symptoms}
                placeholder="For example: yellow leaves, brown spots..."
              />

              {errors.symptoms && (
                <span className="error">
                  {errors.symptoms}
                </span>
              )}
            </label>

            {/* IMAGE UPLOAD */}
            <div className="form-field">
              <label htmlFor="plantImage">
                Plant / Leaf Image (optional)
              </label>

              <div
                style={{
                  border: '1px dashed #8cae91',
                  borderRadius: '12px',
                  padding: '16px',
                  marginTop: '8px',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                    marginBottom: '10px',
                  }}
                >
                  <ImagePlus size={22} />
                  <span>Upload a clear plant image</span>
                </div>

                <input
                  ref={fileInputRef}
                  id="plantImage"
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  onChange={selectImage}
                  disabled={loading || saving}
                  aria-invalid={!!errors.image}
                />

                <p
                  style={{
                    fontSize: '12px',
                    marginTop: '8px',
                    opacity: 0.75,
                  }}
                >
                  JPG, PNG or WebP. Maximum 5 MB.
                </p>

                {errors.image && (
                  <p className="error" role="alert">
                    {errors.image}
                  </p>
                )}

                {preview && (
                  <div
                    style={{
                      marginTop: '12px',
                      position: 'relative',
                      maxWidth: '260px',
                    }}
                  >
                    <img
                      src={preview}
                      alt="Selected plant preview"
                      style={{
                        display: 'block',
                        width: '100%',
                        maxHeight: '220px',
                        objectFit: 'contain',
                        borderRadius: '10px',
                      }}
                    />

                    <button
                      type="button"
                      onClick={removeImage}
                      disabled={loading || saving}
                      aria-label="Remove selected image"
                      style={{
                        position: 'absolute',
                        top: '8px',
                        right: '8px',
                        border: 'none',
                        borderRadius: '50%',
                        padding: '6px',
                        cursor: 'pointer',
                        background: '#ffffff',
                        color: '#222222',
                      }}
                    >
                      <X size={16} />
                    </button>

                    <p
                      style={{
                        fontSize: '12px',
                        marginTop: '6px',
                        overflowWrap: 'anywhere',
                      }}
                    >
                      {image?.name}
                    </p>
                  </div>
                )}
              </div>
            </div>

            <button
              className="button"
              type="submit"
              disabled={
                loading ||
                saving ||
                retrySeconds > 0 ||
                Boolean(errors.image)
              }
            >
              {loading ? (
                <>
                  <LoaderCircle
                    className="spin"
                    size={18}
                  />
                  Analyzing plant and image...
                </>
              ) : retrySeconds > 0 ? (
                <>Try again in {retrySeconds}s</>
              ) : (
                <>
                  <ScanSearch size={18} />
                  {image
                    ? 'Analyze Plant & Image'
                    : 'Analyze Plant'}
                </>
              )}
            </button>
          </form>

          {apiError && (
            <p
              className="notice error-box"
              role="alert"
            >
              <AlertCircle size={18} />
              {apiError}
            </p>
          )}
        </article>

        <article className="card result-card">
          <h2>Plant health analysis</h2>

          {!result && !loading && (
            <div className="empty">
              <ScanSearch size={42} />
              <p>
                Submit your plant details and optionally
                upload an image to see plant care guidance.
              </p>
            </div>
          )}

          {loading && (
            <div className="empty">
              <LoaderCircle
                className="spin"
                size={42}
              />
              <p>
                {image
                  ? 'Reviewing plant details and image...'
                  : 'Reviewing your plant details...'}
              </p>
            </div>
          )}

          {result && (
            <div className="result">
              <span className="demo-label">
                {guidanceLabel}
              </span>

              {analyzedImageName && (
                <p
                  style={{
                    fontSize: '13px',
                    marginTop: '10px',
                  }}
                >
                  <CheckCircle2
                    size={16}
                    style={{
                      display: 'inline',
                      verticalAlign: 'middle',
                      marginRight: '6px',
                    }}
                  />
                  Image analyzed: {analyzedImageName}
                </p>
              )}

              <h4>Possible Issue</h4>
              <h3>{result.possible_issue}</h3>

              <h4>Explanation</h4>
              <p>{result.explanation}</p>

              <h4>Care Suggestions</h4>
              <ul>
                {result.care_suggestions.map(
                  (suggestion, index) => (
                    <li key={`${index}-${suggestion}`}>
                      {suggestion}
                    </li>
                  )
                )}
              </ul>

              <h4>Expert Advice</h4>

              {result.expert_advice_needed === true && (
                <p
                  className="notice error-box"
                  role="alert"
                >
                  <AlertCircle size={18} />
                  Expert agricultural advice is recommended.
                </p>
              )}

              <p>{result.expert_advice}</p>

              <p className="disclaimer">
                This analysis is general guidance, not
                a confirmed plant disease diagnosis.
              </p>

              <button
                className="button"
                type="button"
                onClick={save}
                disabled={saving || saved || loading}
              >
                {saving ? (
                  <>
                    <LoaderCircle
                      className="spin"
                      size={18}
                    />
                    Saving...
                  </>
                ) : saved ? (
                  <>
                    <CheckCircle2 size={18} />
                    Saved to My Plants
                  </>
                ) : (
                  <>
                    <Save size={18} />
                    Save to My Plants
                  </>
                )}
              </button>

              {saved && analyzedImageName && (
                <p
                  className="disclaimer"
                  style={{ marginTop: '10px' }}
                >
                  Analysis saved successfully.
                  Image storage will be enabled in
                  the next backend update.
                </p>
              )}
            </div>
          )}
        </article>
      </div>
    </section>
  );
}
