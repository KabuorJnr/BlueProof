# Fairness audit: dark patterns, hidden fees, fake reviews

The three things on this list are usually found in consumer products that take
money. BlueProof gives money out, so a straight reading of the checklist would
return "not applicable" three times. That reading would miss the point. A
system that pays people has its own version of each failure, and those versions
are what was looked for.

---

## Hidden fees

**Finding: there are none, and the code proves it rather than promising it.**

`payout_per_verified_event` is a flat KSh 150 per verified submission and the
monitor receives all of it. `services/payouts.py` sends exactly that amount;
there is no platform fee, commission, deduction or rounding in the project's
favour anywhere in the backend. Every ledger line carries `amount_paid`, so the
monitor's share of each verified record is visible to anyone reading the
ledger rather than inferred.

The one charge that does exist is Safaricom's B2C transaction tariff, which is
paid by the project's shortcode, not deducted from the monitor.

**The real risk here was never a hidden fee. It was a gap between what a
monitor expects and what they receive.** A monitor walks to a plot and
photographs it under a five shot protocol; if the submission is escalated or
the plot was already paid this cycle, nothing arrives. The verdict screen
therefore states the outcome and every reason for it, and the Wallet shows the
monitor's own paid, pending and under-review submissions, not project totals.

## Dark patterns

**Finding: none present. Two absences worth keeping deliberately.**

Searched for and not found: countdown timers, false scarcity, pre-ticked
consent, roach motels, confirmshaming, disguised advertisements, auto-renewal,
misdirection in button hierarchy, forced continuity, hidden opt-outs.

**Consent is not pre-ticked, and refusing it ends the flow honestly.** `enrol`
rejects a submission without consent and stores nothing, rather than creating
the record and setting a flag. There is no path that enrols somebody who did not
agree.

**Deletion is a real button, not a maze.** It is one endpoint, it works, and it
does not route through an email address that a founder may not read for a week.
It does require typing FUTA, which is friction, and the distinction is worth
being explicit about: friction that protects somebody from an irreversible
accident is not a dark pattern, friction that protects the company from a
decision the user has already made is. This is the first kind.

**One asymmetry was found and left in place, with a reason.** A submission that
fails verification pays nothing, and the monitor has already done the work of
walking to the plot. That is a genuine cost falling on the person least able to
bear it. It is not a dark pattern, because nothing about it is hidden: the
verdict screen lists every reason, distinguishes a species disagreement from
other causes, and says explicitly that this is not the monitor's fault. But it
is a real hardship, and it needs a policy answer, not a design one. A per visit
floor, paid whether or not verification passes, is the obvious candidate and the
budget should carry it.

## Fake reviews and unsupported endorsements

**Finding: no reviews or testimonials exist anywhere in BlueProof.**

The app has no ratings feature, testimonial section or user generated content.
There is nothing to fake.

The endorsement risk lives in pitch material, not the product. Do not list
KMFRI, Mikoko Pamoja, KFS or any CFA as partners until they have agreed in
writing (`docs/risks-and-open-questions.md`). Demo people in `seed.py` are
fictional, and any walkthrough built on them must say so where the audience can
read it.

## What is genuinely not applicable

**Refund policy.** Nothing is sold to a consumer. Money flows outward, from the
project to monitors. There is nothing to refund, and publishing a refund policy
would imply a transaction that does not exist. What replaces it is a **payment
dispute process**: what a monitor does when a payment fails or a verdict is
thought wrong. That is in the terms of service, and the review queue gives it a
mechanism: every escalated submission is decided by a named reviewer with a
written reason.

**Unsubscribe links in emails.** BlueProof sends no email. There is no mail
library in the requirements, no SMTP configuration and no template. If messaging
is added later it will be SMS or WhatsApp, where the equivalent obligation is a
working STOP keyword, and the terms commit to honouring one from the first
message sent.

Both of these are written down rather than left blank, because "we didn't think
we needed one" and "we established we don't need one" look identical in an
empty document and are not the same thing.
