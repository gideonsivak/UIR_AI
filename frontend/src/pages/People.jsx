
import { useEffect, useState } from 'react';
import {
  ArrowRight,
  CheckCircle2,
  UserRound,
} from 'lucide-react';
import { Link } from 'react-router-dom';

import api from '../services/api';
import {
  clearCurrentUserId,
  getCurrentUserId,
  setCurrentUserId,
} from '../utils/storage';

export default function People() {
  const [form, setForm] = useState({
    name: '',
    email: '',
  });

  const [errors, setErrors] = useState({});
  const [saved, setSaved] = useState(false);
  const [message, setMessage] = useState('');
  const [userId, setUserId] = useState(getCurrentUserId());

  useEffect(() => {
    if (!userId) return;

    api
      .get(`/api/users/${userId}`)
      .then(({ data }) => {
        setForm({
          name: data.name,
          email: data.email,
        });
      })
      .catch((err) => {
        if (err.response?.status === 404) {
          clearCurrentUserId();
          setUserId(null);
          setMessage(
            'Your saved profile is no longer available. Please save it again.'
          );
        } else {
          setMessage(
            'Unable to load your profile right now.'
          );
        }
      });
  }, [userId]);

  const submit = async (e) => {
    e.preventDefault();

    const next = {};

    if (!form.name.trim()) {
      next.name = 'Please enter your name.';
    }

    if (!/^\S+@\S+\.\S+$/.test(form.email)) {
      next.email = 'Enter a valid email address.';
    }

    setErrors(next);

    if (Object.keys(next).length) return;

    setMessage('');

    try {
      const payload = {
        name: form.name.trim(),
        email: form.email.trim(),
      };

      const { data } = userId
        ? await api.put(`/api/users/${userId}`, payload)
        : await api.post('/api/users', payload);

      if (!userId) {
        setCurrentUserId(data.id);
        setUserId(data.id);
      }

      setForm({
        name: data.name,
        email: data.email,
      });

      setSaved(true);

      setTimeout(() => {
        setSaved(false);
      }, 3000);
    } catch (err) {
      if (err.response?.status === 404) {
        clearCurrentUserId();
        setUserId(null);
      }

      setMessage(
        err.response?.data?.detail ||
          'Unable to save your information. Please try again.'
      );
    }
  };

  return (
    <section>
      <div className="page-heading">
        <p className="eyebrow">YOUR GROWING SPACE</p>

        <h1>People</h1>

        <p>
          Set up your profile and begin caring with confidence.
        </p>
      </div>

      <div className="two-cards people-cards">
        {/* WELCOME CARD */}
        <article className="card welcome-card">
          <div className="icon-badge">
            <UserRound />
          </div>

          <p className="eyebrow">WELCOME</p>

          {/* UPDATED WELCOME HEADING */}
          <h2>
            Welcome to GIDEON PLANT

            {form.name.trim() && (
              <span
                style={{
                  display: 'block',
                  marginTop: '10px',
                  color: '#085930',
                  overflowWrap: 'anywhere',
                }}
              >
                {form.name.trim()}.
              </span>
            )}
          </h2>

          <p>
            Get approachable, AI-ready guidance to help
            your plants thrive, one observation at a time.
          </p>

          <Link className="button" to="/plant-check">
            Check a plant
            <ArrowRight size={18} />
          </Link>
        </article>

        {/* USER INFORMATION CARD */}
        <article className="card">
          <h2>Your information</h2>

          <p className="muted">
            Your profile is saved by the local app backend.
          </p>

          <form onSubmit={submit} noValidate>
            <label>
              Name

              <input
                value={form.name}
                onChange={(e) => {
                  setForm({
                    ...form,
                    name: e.target.value,
                  });
                }}
                aria-invalid={!!errors.name}
              />

              {errors.name && (
                <span className="error">
                  {errors.name}
                </span>
              )}
            </label>

            <label>
              Email

              <input
                type="email"
                value={form.email}
                onChange={(e) => {
                  setForm({
                    ...form,
                    email: e.target.value,
                  });
                }}
                aria-invalid={!!errors.email}
              />

              {errors.email && (
                <span className="error">
                  {errors.email}
                </span>
              )}
            </label>

            <button className="button" type="submit">
              {userId
                ? 'Update information'
                : 'Save information'}
            </button>

            {saved && (
              <span className="saved">
                <CheckCircle2 size={17} />
                Saved successfully
              </span>
            )}

            {message && (
              <p className="notice error-box">
                {message}
              </p>
            )}
          </form>
        </article>
      </div>
    </section>
  );
}
