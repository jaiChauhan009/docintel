import type { DocumentSummary } from "../lib/api";

export function DocumentList({
  documents,
  selectedId,
  onSelect,
}: {
  documents: DocumentSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="card">
      <strong>Your documents ({documents.length})</strong>
      <table style={{ marginTop: 10 }}>
        <thead>
          <tr>
            <th>File</th>
            <th>Type</th>
            <th>Status</th>
            <th>Confidence</th>
            <th>Uploaded</th>
          </tr>
        </thead>
        <tbody>
          {documents.length === 0 && (
            <tr><td colSpan={5} className="muted">nothing uploaded yet</td></tr>
          )}
          {documents.map((d) => (
            <tr
              key={d.id}
              className="clickable"
              style={{ background: d.id === selectedId ? "#eef4ff" : undefined }}
              onClick={() => onSelect(d.id)}
            >
              <td>{d.file_name}</td>
              <td>{d.document_type}</td>
              <td><span className={`badge ${d.status}`}>{d.status}</span></td>
              <td>{d.confidence ?? "—"}</td>
              <td className="muted">{new Date(d.created_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
