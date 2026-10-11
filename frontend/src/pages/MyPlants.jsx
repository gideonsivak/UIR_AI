
import { useCallback, useEffect, useState } from 'react';
import {
  AlertCircle,
  Eye,
  LoaderCircle,
  Sprout,
  Trash2,
  X,
} from 'lucide-react';

import api from '../services/api';
import { getCurrentUserId } from '../utils/storage';

const getErrorMessage = (err, fallback) => {
  const detail = err.response?.data?.detail;

  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }

  return fallback;
};

const formatDate = (value) => {
  if (!value) return 'Unknown date';

  const date = new Date(value);

  return Number.isNaN(date.getTime())
    ? 'Unknown date'
    : date.toLocaleDateString();
};

export default function MyPlants() {
  const [plants, setPlants] = useState([]);
  const [selected, setSelected] = useState(null);

  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState(null);

  const userId = getCurrentUserId();

  const load = useCallback(async () => {
    if (!userId) {
      setPlants([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError('');

    try {
      const { data } = await api.get('/api/plants', {
        params: {
          user_id: userId,
        },
      });

      if (!Array.isArray(data)) {
        throw new Error('Invalid plant list response.');
      }

      setPlants(data);
    } catch (err) {
      setError(
        getErrorMessage(
          err,
          'Unable to load saved plants. Please try again.'
        )
      );
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    load();
  }, [load]);

  const remove = async (plantId) => {
    if (deletingId !== null) return;

    const confirmed = window.confirm(
      'Delete this saved plant analysis?'
    );

    if (!confirmed) return;

    setDeletingId(plantId);
    setError('');

    try {
      await api.delete(`/api/plants/${plantId}`);

      setPlants((previous) =>
        previous.filter((plant) => plant.id !== plantId)
      );

      setSelected((previous) =>
        previous?.id === plantId ? null : previous
      );
    } catch (err) {
      setError(
        getErrorMessage(
          err,
          'Unable to delete this plant. Please try again.'
        )
      );
    } finally {
      setDeletingId(null);
    }
  };

  const closeDetails = () => {
    setSelected(null);
  };

  useEffect(() => {
    if (!selected) return undefined;

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        closeDetails();
      }
    };

    window.addEventListener('keydown', handleKeyDown);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [selected]);

  return (
    <section>
      <div className="page-heading">
        <p className="eyebrow">YOUR COLLECTION</p>
        <h1>My Plants</h1>
        <p>
          Saved plant checks are kept by the local app backend.
        </p>
      </div>

      {error && (
        <p className="notice error-box" role="alert">
          <AlertCircle size={18} />
          {error}
        </p>
      )}

      {!userId ? (
        <div className="card empty large">
          <Sprout size={50} />
          <h2>Save your profile first</h2>
          <p>
            Visit the People page to save your name and email
            before adding plants.
          </p>
        </div>
      ) : loading ? (
        <div className="card empty large">
          <LoaderCircle className="spin" size={42} />
          <p>Loading your saved plants...</p>
        </div>
      ) : plants.length === 0 ? (
        <div className="card empty large">
          <Sprout size={50} />
          <h2>No saved plants yet</h2>
          <p>
            Analyze a plant and save its guidance to build
            your collection.
          </p>
        </div>
      ) : (
        <div className="plant-list">
          {plants.map((plant) => (
            <article
              className="card plant-card"
              key={plant.id}
            >
              <div>
                <p className="eyebrow">
                  {plant.plant_type}
                </p>

                <h2>{plant.plant_name}</h2>

                {plant.location && (
                  <p className="muted">
                    {plant.location}
                  </p>
                )}

                <p>
                  <b>Symptoms:</b> {plant.symptom}
                </p>

                <p className="muted">
                  Analyzed {formatDate(plant.created_at)}
                </p>

                {plant.analysis && (
                  <>
                    <p className="issue">
                      <b>Possible issue:</b>{' '}
                      {plant.analysis.possible_issue}
                    </p>

                    {plant.analysis.expert_advice_needed === true && (
                      <p className="notice error-box">
                        <AlertCircle size={17} />
                        Expert advice recommended
                      </p>
                    )}
                  </>
                )}
              </div>

              <div className="actions">
                <button
                  className="button secondary"
                  type="button"
                  onClick={() => setSelected(plant)}
                >
                  <Eye size={17} />
                  View details
                </button>

                <button
                  className="icon-button"
                  type="button"
                  aria-label={`Delete ${plant.plant_name}`}
                  onClick={() => remove(plant.id)}
                  disabled={deletingId !== null}
                >
                  {deletingId === plant.id ? (
                    <LoaderCircle
                      className="spin"
                      size={18}
                    />
                  ) : (
                    <Trash2 size={18} />
                  )}
                </button>
              </div>
            </article>
          ))}
        </div>
      )}

      {selected && (
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={(event) => {
            if (event.target === event.currentTarget) {
              closeDetails();
            }
          }}
        >
          <section
            className="modal card"
            role="dialog"
            aria-modal="true"
            aria-label="Saved plant analysis"
          >
            <button
              className="close"
              type="button"
              onClick={closeDetails}
              aria-label="Close details"
            >
              <X />
            </button>

            <p className="eyebrow">
              {selected.plant_name}
            </p>

            <h2>Plant Details</h2>

            <p>
              <b>Plant Type:</b> {selected.plant_type}
            </p>

            {selected.location && (
              <p>
                <b>Location:</b> {selected.location}
              </p>
            )}

            <p>
              <b>Symptoms:</b> {selected.symptom}
            </p>

            {selected.analysis ? (
              <div className="result">
                <h3>Possible Issue</h3>
                <p>{selected.analysis.possible_issue}</p>

                <h3>Explanation</h3>
                <p>{selected.analysis.explanation}</p>

                <h3>Care Suggestions</h3>

                {Array.isArray(
                  selected.analysis.care_suggestions
                ) ? (
                  <ul>
                    {selected.analysis.care_suggestions.map(
                      (suggestion, index) => (
                        <li key={`${index}-${suggestion}`}>
                          {suggestion}
                        </li>
                      )
                    )}
                  </ul>
                ) : (
                  <p>
                    No structured care suggestions are available.
                  </p>
                )}

                <h3>Expert Advice</h3>

                {selected.analysis.expert_advice_needed === true && (
                  <p
                    className="notice error-box"
                    role="alert"
                  >
                    <AlertCircle size={18} />
                    Expert agricultural advice is recommended.
                  </p>
                )}

                <p>
                  {selected.analysis.expert_advice}
                </p>

                <p className="disclaimer">
                  This analysis is general guidance,
                  not a confirmed plant disease diagnosis.
                </p>
              </div>
            ) : (
              <p>
                No saved analysis is available for this plant.
              </p>
            )}
          </section>
        </div>
      )}
    </section>
  );
}
