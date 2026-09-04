import { useCallback, useEffect, useState } from "react";
import { DocumentDetail } from "../components/DocumentDetail";
import { DocumentList } from "../components/DocumentList";
import { UploadForm } from "../components/UploadForm";
import { api, type DocumentSummary } from "../lib/api";
import { useAuth } from "../lib/auth";

export function Dashboard() {
  const { token, logout } = useAuth();
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!token) return;
    try {
      const page = await api.listDocuments(token);
      setDocuments(page.items);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to load documents");
    }
  }, [token]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, [refresh]);

  return (
    <div className="container">
      <div className="between">
        <h1 style={{ margin: 0 }}>DocIntel</h1>
        <button onClick={logout}>Log out</button>
      </div>
      <p className="muted">Upload invoices, receipts, contracts and bank statements — get structured data back.</p>

      <UploadForm onUploaded={refresh} />
      {error && <div className="card error">{error}</div>}

      <DocumentList documents={documents} selectedId={selectedId} onSelect={setSelectedId} />

      {selectedId && (
        <DocumentDetail
          id={selectedId}
          onClose={() => setSelectedId(null)}
          onChanged={refresh}
        />
      )}
    </div>
  );
}
