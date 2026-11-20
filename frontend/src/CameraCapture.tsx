import { useEffect, useRef, useState } from "react";

import { CameraIcon } from "./icons";

/**
 * A live camera view, captured to a still photo (T-403, NFR-02).
 *
 * `<input capture>` is a mobile-only hint — desktop browsers ignore it and just open the file
 * picker, which is not "take a photo". getUserMedia works the same way on desktop and mobile
 * (both are a secure context: https, or localhost in dev), so this opens a real live preview
 * and snaps a frame to canvas. Where it isn't available — no camera, permission refused, an
 * insecure context — it falls back to the file picker so capture is still possible.
 */
export function CameraCapture({
  onCapture,
  onCancel,
}: {
  onCapture: (file: File) => void;
  onCancel: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const fallbackInput = useRef<HTMLInputElement>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [fallback, setFallback] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setFallback(true);
      return;
    }
    let cancelled = false;
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "environment" }, audio: false })
      .then((s) => {
        if (cancelled) {
          s.getTracks().forEach((t) => t.stop());
          return;
        }
        setStream(s);
      })
      .catch((e: Error) => {
        if (cancelled) return;
        setError(e.message);
        setFallback(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (videoRef.current && stream) videoRef.current.srcObject = stream;
    return () => {
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [stream]);

  useEffect(() => {
    if (fallback) fallbackInput.current?.click();
  }, [fallback]);

  function snap() {
    const video = videoRef.current;
    if (!video) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0);
    canvas.toBlob(
      (blob) => {
        if (blob) onCapture(new File([blob], "capture.jpg", { type: "image/jpeg" }));
      },
      "image/jpeg",
      0.92,
    );
  }

  if (fallback) {
    return (
      <input
        ref={fallbackInput}
        type="file"
        accept="image/*"
        capture="environment"
        aria-label="Take a photo"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onCapture(file);
          else onCancel();
        }}
      />
    );
  }

  return (
    <section className="card">
      <div className="flex flex-col gap-1">
        <h2>Line up the part</h2>
        <p className="muted small">Fill the frame with the part, in good light.</p>
      </div>
      {error && (
        <p className="muted small">Live camera isn't available ({error}); using the file picker instead.</p>
      )}
      <div className="overflow-hidden rounded-xl bg-black">
        {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
        <video ref={videoRef} autoPlay playsInline muted className="block w-full" />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <button type="button" className="primary" onClick={snap} disabled={!stream}>
          <CameraIcon />
          {stream ? "Capture" : "Starting camera…"}
        </button>
        <button type="button" className="secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </section>
  );
}
