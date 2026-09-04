import { useEffect, useState } from "react";
import { api, ApiError, type DocumentDetail as Detail, type DocumentResult } from "../lib/api";
import { useAuth } from "../lib/auth";

export function DocumentDetail({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged: () => void }) {
  const { token } = useAuth();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [result, setResult] = useState<DocumentResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    if (!token) return;
    try {
      const d = await api.getDocument(token, id);
      setDetail(d);
      if (d.status === "COMPLETED") setResult(await api.getResult(token, id));
      else setResult(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "failed to load");
    }
  }

  useEffect(() => {
    load();
    const t = setInterval(load, 2500);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function retry() {
    if (!token) return;
    await api.retryDocument(token, id);
    onChanged();
    load();
  }

  async function remove() {
    if (!token) return;
    await api.deleteDocument(token, id);
    onChanged();
    onClose();
  }

  if (error) return <div className="card error">{error}</div>;
  if (!detail) return <div className="card">Loading…</div>;

  return (
    <div className="card">
      <div className="between">
        <h3 style={{ margin: 0 }}>{detail.file_name}</h3>
        <button onClick={onClose}>Close</button>
      </div>
      <div className="grid2" style={{ marginTop: 12 }}>
        <div><span className="muted">Status</span><br /><span className={`badge ${detail.status}`}>{detail.status}</span></div>
        <div><span className="muted">Type</span><br />{detail.document_type}</div>
        <div><span className="muted">Confidence</span><br />{detail.confidence ?? "—"}</div>
        <div><span className="muted">Retry count</span><br />{detail.retry_count}</div>
      </div>

      {detail.error_message && (
        <div style={{ marginTop: 12 }}>
          <span className="muted">Error</span>
          <p className="error">{detail.error_message}</p>
        </div>
      )}

      <div className="row" style={{ marginTop: 12 }}>
        {detail.status === "FAILED" && <button className="primary" onClick={retry}>Retry processing</button>}
        <button onClick={remove}>Delete</button>
      </div>

      <h4>Processing attempts</h4>
      <table>
        <thead>
          <tr><th>#</th><th>Status</th><th>Stage</th><th>Error</th><th>Duration</th></tr>
        </thead>
        <tbody>
          {detail.attempts.length === 0 && (
            <tr><td colSpan={5} className="muted">no attempts yet</td></tr>
          )}
          {detail.attempts.map((a) => (
            <tr key={a.attempt_number}>
              <td>{a.attempt_number}</td>
              <td>{a.status}</td>
              <td>{a.stage ?? "—"}</td>
              <td className="muted">{a.error_message ?? "—"}</td>
              <td>{a.duration_ms != null ? `${a.duration_ms} ms` : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {result && (
        <>
          <h4>Extracted data (confidence {result.confidence})</h4>
          <pre>{JSON.stringify(result.extracted_data, null, 2)}</pre>
        </>
      )}
    </div>
  );
}
