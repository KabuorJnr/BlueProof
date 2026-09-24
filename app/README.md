# BlueProof field app

A progressive web app for community mangrove monitors. Open it from a link or a
QR code, walk a plot, photograph it under a guided protocol, and get the
submission verified and paid. No Play Store account, no download, works on cheap
Android handsets, and keeps working when the network does not.

React with lucide-react icons, on a white glass over dark green design system.

## Run it

```bash
cd app
npm install
npm run dev          # http://localhost:5174
npm run build
npm run preview
```

Start the backend first, then open Mipangilio (Settings) and point the app at
your backend URL. `VITE_API_BASE` bakes a default in at build time.

## The five shot protocol is the product

This is not a camera with a submit button. It walks the monitor through the
protocol in `docs/field-photo-protocol.md`: the plot marker, a wide shot, the
close shot, the leaf shot, and a problem shot. Tide and light guidance sit on
the same screen.

The reason is specific. The published evidence on vision models in the field is
that performance is dominated by **image legibility**, not by the difficulty of
telling species apart. Legibility is something a protocol can fix and taxonomy
is not, so the highest leverage intervention available to this app is improving
the photograph at the moment of capture. The close shot is the frame submitted
as evidence, because it is the one the species assessment depends on.

## Corroboration, not determination

The app sends the monitor's declared species alongside the photograph. If the
model disagrees with the declaration, the submission is **escalated to human
review and pays nothing**. It does not overwrite the declaration.

The monitor is told exactly that, in Swahili: you said one thing, the image read
as another, we are not changing your answer because you are the one who stood at
the plot, a person will look at it.

Three independent reasons the system declines rather than guesses: confidence
below threshold, condition assessed as unclear, or a species dispute. This is a
deliberate response to the published finding that general purpose vision models
fabricate species names at meaningful rates. An attestation product that guesses
is worth nothing.

## Offline

A submission captured with no signal is queued **with its photograph** in
IndexedDB, so when it eventually reaches the backend it is still verified
against the real image. An attestation derived from anything other than the
photograph is not evidence, which is why the queue stores the blob rather than a
description.

## Screens

Viwanja lists the plots at the site. Tapping one opens the guided capture.
Verdict shows what the model saw, the confidence meter, and either the payment
or the reason for escalation. Pochi shows earnings, seedlings verified, hectares
monitored and cutting alerts. Eneo shows satellite observations, how many were
lost to cloud, and any canopy loss alerts, with the standing reminder that
satellite sees hectares and not seedlings. Foleni is the offline queue.

## Known limitations

**Only the close shot reaches the backend.** The other four are captured and
held on the device. Multi-image submission needs a backend change; the protocol
still improves the evidence shot, which is the one that matters most.

**Live satellite is not wired.** The Eneo screen reads a generated NDVI series,
not Sentinel-2. Do not present it as live data.

**Llama has never seen a real mangrove photo.** The verification path is built
and tested, but against a deterministic mock. Whether a vision model can
actually discriminate these species from a phone photograph in a creek is
untested, and the literature gives real reason for caution. That is what the
100 photo evaluation is for.

## Testing

An end to end Chromium test at phone viewport covers the plot list, the guided
capture with a real image upload, submission, the verdict, the wallet and the
satellite refresh, including the species dispute path.
