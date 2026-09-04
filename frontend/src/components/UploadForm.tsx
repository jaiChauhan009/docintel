import { useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";

export function UploadForm({ onUploaded }: { onUploaded: () => void }) {
  const { token } = useAuth();
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function upload() {
    const file = inputRef.current?.files?.[0];
    if (!file || !token) return;
    setBusy(true);
    setError(null);
    try {
      await api.uploadDocument(token, file);
      if (inputRef.current) inputRef.current.value = "";
      onUploaded();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <div className="between">
        <div>
          <strong>Upload a document</strong>
          <div className="muted">PDF, PNG, JPEG, TIFF or plain text — up to the server limit.</div>
        </div>
        <div className="row">
          <input ref={inputRef} type="file" accept=".pdf,.png,.jpg,.jpeg,.tiff,.txt" style={{ width: "auto" }} />
          <button className="primary" onClick={upload} disabled={busy}>
            {busy ? "Uploading..." : "Upload"}
          </button>
        </div>
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
