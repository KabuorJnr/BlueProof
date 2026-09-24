# Data inventory: BlueProof

Every piece of personal data the system holds, why it exists, and what happens
to it. Built by reading the models, not by recalling the design.

The test applied to each field was narrow and unforgiving: **name the specific
thing that stops working if this field is removed.** Anything that could not
answer was taken out or replaced with a pseudonym. Two fields failed that test
and both are recorded below under what was removed.

---

## Who this data is about

Community monitors, most of them young, some of them under 18. That last fact
is not incidental. The Youth Climate Action Fund targets ages 15 to 24, so a
monitor under 18 is an expected participant rather than an edge case, and the
system is built on that assumption instead of discovering it during a pilot.

## What is held, and why

### `user` — the only table where a person is identifiable

| Field | Purpose | Removed if deleted |
|---|---|---|
| `name` | Addressing a person, and resolving a dispute about a submission | Yes |
| `phone` | The M-Pesa number. Payment does not work without it | Yes |
| `cfa` | Which Community Forest Association, for coordination | Yes |
| `public_ref` | The pseudonym everything else uses | Yes |
| `role` | Monitor, CFA lead, verifier, admin | Yes |
| `consent_version`, `consented_at` | Demonstrating consent, which the Act requires the controller to be able to do | Yes |
| `is_minor` | Whether a guardian had to agree | Yes |
| `guardian_name`, `guardian_phone` | Reaching the adult who consented | Yes |

**There is no date of birth, and that is deliberate.** The only question this
system ever needs answered is whether a guardian must consent. A date of birth
answers a question nobody is asking, is more sensitive than the answer that is
needed, and stays sensitive forever. `is_minor` is a boolean that stops being
true on its own.

### `monitoringevent` — what was submitted

Holds `monitor_id`, plot, coordinates, photo reference, the verdict, the
confidence and the reasoning. No name, no phone number. After a deletion the
`monitor_id` points at a row that no longer exists.

Coordinates here are the plot's, not the person's. A monitoring plot's location
is a fixed, project-known fact; recording it does not reveal where anybody
lives.

### `ledgerentry` — the product

| Field | Note |
|---|---|
| `monitor_ref` | A pseudonym. **This used to be `monitor_name`.** |
| `verification_source` | Which verifier answered. Added so a record can be audited rather than merely believed |
| `plot_code`, `species`, `seedlings_verified`, `health` | The environmental record |
| `lat`, `lon` | The plot |
| `amount_paid`, `recorded_at` | The transaction |

### `payment`

Holds the phone number and the amount. This is the table that survives a
deletion request, because payment records must be retained for seven years, and
the deletion response says so plainly rather than silently keeping them.

---

## What was removed

**`ledgerentry.monitor_name`.** The ledger is exported, shown to funders and
sold to credit buyers, and each line already carried a plot code, a date and
coordinates accurate to a few metres. Adding a real name turned an
environmental record into a published statement of where an identifiable young
person stood on a given morning, repeated for every morning they worked. For a
monitor who reports illegal cutting in their own community that is not a
theoretical concern, it is a safety one.

Nothing of value was lost. A buyer can still see that one person monitored these
plots consistently. An auditor can still follow a disputed line back through
`user.public_ref`, as long as they have lawful access to the `user` table. What
disappeared is the ability of anyone holding an exported spreadsheet to do the
same.

**The unused `CO2_PER_KG` style blanket assumption** is a claims issue rather
than a data issue and is dealt with in the claims register.

## What was never collected, and should stay that way

National ID number. Date of birth. Location outside a submission. Contacts,
photo library, or anything else the handset would offer. Any data from any other
service. There is no analytics SDK, no crash reporter and no third party script
in the app, which the third party audit demonstrates with a recorded network
trace rather than asserting.

## Where data goes

| Destination | What | When |
|---|---|---|
| The backend the user configured | Everything | Always |
| An inference provider | The photograph, base64 encoded | Only when `LLAMA_API_URL` is set. Currently unset |
| Safaricom Daraja | Phone number, amount, reference | Only in sandbox or live mode. Currently mock |
| Copernicus / Sentinel Hub | Site polygon and date range. No personal data | Only when credentials are set. Currently unset |

The inference provider is the one that deserves a decision rather than a
configuration change. Enabling it sends photographs taken by young people, which
may include their hands, their faces, their homes or their neighbours, out of
the country to a third party. Before that is switched on, that provider needs
its own assessment: where it processes, how long it retains, whether it trains
on what it receives. A provider that retains photographs for training is not
usable here without specific, informed consent from each monitor, and probably
not usable at all for a cohort that includes minors.

## On the device

`localStorage` holds the backend URL. `sessionStorage` holds the plot being
worked on and the last verdict, and is cleared when the tab closes. IndexedDB
holds submissions captured offline, including the photograph, until they sync.

No cookies are set by the app. Not "only essential cookies": none.

All of it is functional. None of it is analytics, none is advertising, and none
of it leaves the phone except as part of a submission the monitor made.

## Retention

| Data | Kept | Why |
|---|---|---|
| Name, phone, guardian details | Until deletion is requested, or the project ends | No reason to hold it longer |
| Submissions and verdicts | Indefinitely, pseudonymous | The environmental record is the point |
| Ledger entries | Indefinitely, pseudonymous | Sold and audited |
| Payment records | Seven years | Financial retention rules |
| Photographs | **Undecided, and that is a gap** | See below |

**The photograph retention question is open and needs answering before the
pilot.** A photograph is the evidence, so it cannot be discarded immediately, and
it may contain faces. The likely answer is: retain for the verification period
and any dispute window, then keep the verdict and discard the image. Nobody has
made that decision yet, and it should be made by a person rather than by
default.

## Still to do before any real person is enrolled

Registration with the Office of the Data Protection Commissioner, which applies
to controllers processing personal data in Kenya and is not optional once real
monitors are enrolled. A named data protection contact. The photograph retention
decision above. An assessment of whichever inference provider is chosen. And the
consent wording itself reviewed by somebody who is not its author.
