/**
 * Camera capture.
 *
 * Two paths, because reliability beats elegance in the field:
 *  - a live getUserMedia preview where the browser allows it
 *  - a plain file input with capture="environment", which always works and
 *    hands off to the phone's own camera app
 *
 * Images are downscaled and re-encoded before upload. A modern phone photo is
 * several megabytes; on a metered connection at the coast that is both slow and
 * expensive, and the grader does not need the resolution.
 */

const MAX_EDGE = 1280;
const QUALITY = 0.72;

export async function compress(fileOrBlob) {
  const bitmap = await createImageBitmap(fileOrBlob);
  const scale = Math.min(1, MAX_EDGE / Math.max(bitmap.width, bitmap.height));
  const w = Math.round(bitmap.width * scale);
  const h = Math.round(bitmap.height * scale);

  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  canvas.getContext('2d').drawImage(bitmap, 0, 0, w, h);
  bitmap.close?.();

  return new Promise((resolve) =>
    canvas.toBlob((blob) => resolve(blob || fileOrBlob), 'image/jpeg', QUALITY)
  );
}

export function fileInput(onPicked) {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = 'image/*';
  input.capture = 'environment';
  input.className = 'visually-hidden';
  input.addEventListener('change', async () => {
    const file = input.files && input.files[0];
    if (!file) return;
    onPicked(await compress(file), URL.createObjectURL(file));
    input.value = '';
  });
  return input;
}

/** Live preview. Returns a stop() function, or null if unavailable. */
export async function startPreview(videoEl) {
  if (!navigator.mediaDevices?.getUserMedia) return null;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' } },
      audio: false,
    });
    videoEl.srcObject = stream;
    await videoEl.play().catch(() => {});
    return () => stream.getTracks().forEach((t) => t.stop());
  } catch {
    // Permission denied, no camera, or an insecure origin. The file input path
    // still works, so this is not an error the monitor needs to see.
    return null;
  }
}

export async function grabFrame(videoEl) {
  const canvas = document.createElement('canvas');
  const scale = Math.min(1, MAX_EDGE / Math.max(videoEl.videoWidth, videoEl.videoHeight));
  canvas.width = Math.round(videoEl.videoWidth * scale);
  canvas.height = Math.round(videoEl.videoHeight * scale);
  canvas.getContext('2d').drawImage(videoEl, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise((r) => canvas.toBlob(r, 'image/jpeg', QUALITY));
  return { blob, url: canvas.toDataURL('image/jpeg', 0.5) };
}

/**
 * Best effort location. Never blocks a submission.
 *
 * The geolocation `timeout` option only bounds acquiring a fix AFTER permission
 * has been granted. If the user never answers the permission prompt, neither
 * callback ever fires and the promise hangs forever. That would strand a
 * monitor on a dead screen, so we impose our own hard deadline and resolve
 * null regardless of what the browser does.
 */
export function getPosition(timeout = 8000) {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve(null);

    let settled = false;
    const done = (value) => {
      if (settled) return;
      settled = true;
      resolve(value);
    };

    const deadline = setTimeout(() => done(null), timeout);
    navigator.geolocation.getCurrentPosition(
      (p) => {
        clearTimeout(deadline);
        done({ lat: p.coords.latitude, lon: p.coords.longitude });
      },
      () => {
        clearTimeout(deadline);
        done(null);
      },
      { enableHighAccuracy: true, timeout, maximumAge: 60000 }
    );
  });
}
