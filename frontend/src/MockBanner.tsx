/** Shown whenever the app is running against mock data (VITE_USE_MOCKS, default on). */
export function MockBanner({ onPreview }: { onPreview?: () => void }) {
  return (
    <div className="mock-banner" role="status">
      Demo mode: showing mock data, not a live backend.
      {onPreview && (
        <>
          {" "}
          <button type="button" className="link !min-h-0 !p-0" onClick={onPreview}>
            Preview every UI state
          </button>
        </>
      )}
    </div>
  );
}
