import { useRef, useState } from "react";
import { uploadDocument } from "../api";
import PanelTitle from "../components/PanelTitle";
import StatusMessage from "../components/StatusMessage";

export default function UploadPage() {
  const [status, setStatus] = useState("idle"); // idle | uploading | success | error
  const [result, setResult] = useState(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef(null);

  const handleFile = async (file) => {
    if (!file) return;
    setStatus("uploading");
    setResult(null);
    try {
      const response = await uploadDocument(file);
      if (response.success) {
        setResult(response);
        setStatus("success");
      } else {
        setErrorMessage(response.reason || "Upload failed.");
        setStatus("error");
      }
    } catch (err) {
      setErrorMessage(err.message || "Something went wrong.");
      setStatus("error");
    }
  };

  const onDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    handleFile(e.dataTransfer.files?.[0]);
  };

  return (
    <div className="page-content">
      <PanelTitle
        eyebrow="Knowledge base"
        heading="Upload Document"
        sub="Add a policy document, report, or other reference material — it becomes searchable evidence for future decisions."
      />

      <div
        className={`upload-dropzone ${isDragging ? "is-dragging" : ""}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={onDrop}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
        }}
      >
        <div className="upload-dropzone__title">Drop a PDF here, or click to browse</div>
        <div className="upload-dropzone__hint">PDF files with real, selectable text only — scanned images aren't supported</div>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          style={{ display: "none" }}
          onChange={(e) => handleFile(e.target.files?.[0])}
        />
      </div>

      {status === "uploading" && (
        <div style={{ marginTop: "1.25rem" }}>
          <StatusMessage tone="loading" title="Uploading and indexing…" body="Extracting text and splitting it into searchable chunks." />
        </div>
      )}

      {status === "success" && result && (
        <div style={{ marginTop: "1.25rem" }}>
          <StatusMessage
            tone="success"
            title="Document indexed"
            body={`${result.filename} — ${result.chunks_stored} chunks stored (document #${result.document_id}).`}
          />
        </div>
      )}

      {status === "error" && (
        <div style={{ marginTop: "1.25rem" }}>
          <StatusMessage tone="error" title="Upload failed" body={errorMessage} />
        </div>
      )}
    </div>
  );
}
