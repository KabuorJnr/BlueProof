# Risks and open questions

Say these out loud before a judge or a funder asks. Naming them is a strength.

## Technical

**Resolution.** Sentinel-2 at 10 metres detects canopy scale loss, not
individual seedlings. Plot level survival rests entirely on the field
photographs. Do not claim satellite verification of planting survival.

**Cloud.** The Kenyan coast is cloudy. Optical revisit is roughly five days but
usable observations are fewer. Sentinel-1 radar penetrates cloud and is the
right mitigation, not yet implemented.

**Live satellite is built but unvalidated.** The Copernicus Statistical API
path, SCL cloud masking and the measured baseline are implemented and tested
against API-shaped responses, never against a real account. Until a real run
with a real site polygon, do not show the dashboard and imply it is live data.

**Llama verification is unvalidated on real photos.** The prompt is now
bounded (corroborate the declared species, never name it from scratch), and
`tools/llama_eval.py` measures exactly the deployed prompt, sampling and
parsers, including marker reading and same-place judgement when the labels
carry those columns. Two new failure modes to watch: a misread marker is a
false fraud flag, and seasonal change (tide, leaf flush) may be judged as a
different place. Both cost review time, not money. The mock returns plausible
verdicts. Nobody has yet tested a vision model against real Kenyan mangrove plot
photographs, and species discrimination between, say, Ceriops and young
Rhizophora may be genuinely hard from a phone image. This is the single biggest
technical unknown. Test it with 50 real photos before promising accuracy.

## Ecological and methodological

**The CO2 rate is an assumption.** `config.co2_tonnes_per_ha_year` is a
placeholder. Kenyan mangrove sequestration estimates vary widely by species,
age and site. Validate against KMFRI work or an approved Plan Vivo or Verra
methodology before quoting any figure.

**BlueProof is not a registry.** It produces MRV evidence. It does not issue
credits and will not be accredited in the near term. Position as infrastructure
serving existing projects.

## Social and legal

**Land tenure.** Mangroves are government forest reserve land under the Kenya
Forest Service. Any real pilot needs KFS permission and a Community Forest
Association partner. A software demo does not.

**Benefit sharing.** Blue carbon carries a legitimate criticism that little of
the money reaches the people doing the planting. Cutting verification cost could
just as easily increase credit supply without improving what a monitor earns.
Design against this deliberately: publish what a monitor is paid per verified
event, and make that number visible in the ledger rather than buried.

**Consent and imagery.** Photographs taken in and around a community are
personal data in practice. Decide early what is stored, who can see it, and how
long it is kept.

**Do not name partners who have not agreed.** KMFRI, Mikoko Pamoja, KFS and any
CFA belong on a slide only after they have said yes in writing.

## Commercial

**Who actually pays, and how much per hectare monitored, is unvalidated.** The
BlueProof thesis is that MRV cost is the bottleneck. That is an argument, not a
measurement. Test it by asking two or three existing blue carbon projects what
they currently spend on monitoring and verification per year. If the answer is
small, the thesis needs rework.
