import PanelTitle from "../components/PanelTitle";

function UploadPage({ file, setFile, handleUpload, loading }) {
  return (
    <section className="panel upload-panel">
      <PanelTitle eyebrow="Knowledge Base" title="Upload PDF" />
      <form onSubmit={handleUpload} className="upload-box">
        <div>
          <strong>{file ? file.name : "Choose a PDF document"}</strong>
          <span>Policies, reports, support exports, or business notes.</span>
        </div>
        <label className="file-picker">
          Browse File
          <input
            type="file"
            accept="application/pdf"
            onChange={(event) => setFile(event.target.files[0])}
          />
        </label>
        <button className="primary-button" disabled={loading}>
          Upload PDF
        </button>
      </form>
    </section>
  );
}

export default UploadPage;
