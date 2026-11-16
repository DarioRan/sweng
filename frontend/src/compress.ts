/** Client-side photo compression before upload (T-403): at most 2 MB. */

export const MAX_UPLOAD_BYTES = 2 * 1024 * 1024;
export const MAX_SIDE = 1600; // what the detector was trained on; larger only costs upload time

/** The largest JPEG quality, from a fixed ladder, that brings the photo under the limit. */
export async function compressPhoto(file: Blob, maxBytes = MAX_UPLOAD_BYTES): Promise<Blob> {
  // createImageBitmap applies the EXIF rotation, so the upload is the photo as the user saw it.
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();

  let blob: Blob | null = null;
  for (const quality of [0.9, 0.8, 0.7, 0.6, 0.5, 0.4]) {
    blob = await new Promise<Blob | null>((ok) => canvas.toBlob(ok, "image/jpeg", quality));
    if (blob && blob.size <= maxBytes) return blob;
  }
  if (!blob) throw new Error("this browser could not encode the photo");
  return blob; // still over the limit at the lowest quality: rare at 1600 px, sent anyway
}
