# Cookies and storage

**Version 2026-09-18.**

## There are no cookies

The BlueProof app sets no cookies. Not "only essential cookies", not "cookies
you can turn off": none at all. Nothing in the code sets one and nothing in the
app reads one.

This document exists anyway, because a checklist asking for a cookie policy is
really asking a broader question: what is this app keeping on my phone, and who
gets to see it. That question deserves an answer whether or not the mechanism
happens to be a cookie.

## Why there is no consent banner

A banner is required when a site stores things that are not necessary to provide
what the user asked for: analytics, advertising, tracking. This app stores none
of those, because it contains none of those.

Adding a banner anyway would be worse than leaving it out. A dialogue offering a
choice that changes nothing is theatre, and asking somebody to click Accept on a
box with no Reject that does anything is a dark pattern in the ordinary sense of
the term. The honest thing is to say clearly what is stored and why, which is
what follows.

If analytics are ever added, that changes and a real banner becomes necessary:
one that works, that remembers a refusal, and where refusing is as easy as
accepting.

## What is actually stored on the handset

Three things, all of them necessary for the app to work at all.

**The server address** (`blueproof.apiBase`, in `localStorage`). Which backend
the app talks to. You set it yourself on the settings screen. It has to persist,
or the app would have to be reconfigured every time it opened.

**The plot you are working on and your last verdict** (`blueproof.plot`,
`blueproof.verdict`, in `sessionStorage`). These carry information between
screens while you work. They are erased when you close the tab.

**Submissions made with no network** (in IndexedDB), including the photograph,
held until they can be sent.

That last one is the only significant amount of data, and it is worth explaining
why it is there. A submission captured without signal has to keep its
photograph, because a submission verified against a description rather than an
image is not evidence of anything. So the image waits on the phone, and it is
deleted once it has been sent successfully.

## Who can see it

Nobody but you. Browser storage belongs to one site on one browser on one
device. It is not sent anywhere except as part of a submission you made, it does
not follow you to another phone, and we cannot read it remotely.

## Clearing it

Clear the site data in your browser and all of it goes. Do check the queue
screen first: anything still waiting to be sent will be lost, and with it the
work it represents.

## What is not there

No analytics. No advertising or tracking pixel. No social media button. No tag
manager. No crash reporting. No session recorder. No web fonts, so no font host
sees your phone's address. No third party script of any kind.

The app makes network requests to exactly one place: the backend address on the
settings screen. That is verifiable rather than merely claimed: the third party
audit in `docs/third-party-audit.md` records a browser session that visited every
screen and lists every host contacted.
