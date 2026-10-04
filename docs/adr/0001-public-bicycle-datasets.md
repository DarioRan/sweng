# ADR 0001 — Public bicycle datasets: which to adopt, and for what

- **Status:** Proposed
- **Date:** 2026-09-28
- **Deciders:** Sneha Chaudhary, Narmeen Sabah Siddiqui, Dario Ranieri, Yernur Polatbek
- **Issue:** #6 (T-308, Sprint 2, Vision, P1)
- **Related:** frozen component class list (T-306, #11), recorded as ADR 0002
- **Amended:** 2026-10-05: class overlap checked against the frozen list (#11)

---

## Context

The part detector needs to identify bicycle components from a photograph taken by a user. We capture and annotate our own close-up photographs for this, and that remains the primary training set. The open question is whether a public bicycle dataset is worth adopting alongside it as a **pretraining and auxiliary source**: train on a large public set first so the detector begins with bicycle-part visual priors, then fine-tune on our own data.

Two candidates were surveyed against three criteria:

1. **Does it help identify bicycle parts from a photograph?** This is the product requirement (FR-05, FR-07) and the primary criterion. It is deliberately broader than our own drivetrain-and-brake class list: a dataset with a different but genuine bike-part vocabulary can still contribute transferable features.
2. **Is it legally usable?** Licence terms recorded and compatible with §9.6 and NFR-SEC3.
3. **Does it preserve the option of a later 3D or augmented-reality extension?** A recorded forward constraint, not a current requirement.

## Candidates surveyed

### DelftBikes

| | |
|---|---|
| Size | 10,000 bicycle photographs, split 8,000 train / 2,000 test by the authors. 518 MB unzipped; the archive alone is 507 MB |
| Annotation | Bounding boxes for **22 parts** in every image, plus a state label per part |
| The 22 classes | front wheel, back wheel, front mudguard, back mudguard, saddle, **gear case**, **chain**, steer, kickstand, dress guard, lock, front handle, back handle, **front pedal**, **back pedal**, dynamo, front light, back light, back reflector, **front hand brake**, **back hand brake**, bell |
| Part states | intact 60.5 %, absent 19.5 %, occluded 14 %, damaged 6 %. Distribution is comparable across train and test splits |
| Imagery | Real photographs of single parked bicycles, predominantly side-on, in outdoor and indoor settings with varied lighting and backgrounds |
| Creators | Osman Semih Kayhan, Bart Vredebregt, Jan C. van Gemert — Computer Vision Lab, TU Delft, and Aiir Innovations |
| Canonical source | 4TU.ResearchData, DOI [10.4121/14866116.v2](https://doi.org/10.4121/14866116.v2), published 2021-07-05 |
| Paper | Kayhan, Vredebregt & van Gemert (2021), *Hallucination in Object Detection: A Study in Visual Part Verification*, IEEE ICIP 2021. Preprint arXiv:2106.02523 |
| Also used in | The object-detection challenge of the 2nd Visual Inductive Priors workshop, ICCV 2021. Note the paper is ICIP and the challenge an ICCV workshop — two different venues |
| **Licence** | **CC BY-SA 4.0** (creativecommons.org/licenses/by-sa/4.0/). Verified on the 4TU landing page, version 2, on 2026-09-28 |
| Licence implications | Attribution required. No NonCommercial and no NoDerivatives clause, so use as training data is permitted. ShareAlike applies to distributed *adaptations*; whether model weights trained on the data constitute an adaptation is unsettled, and the obligation triggers on distribution, not on use |
| Code | github.com/oskyhn/DelftBikes — paper landing page only: README and two figures, six commits, no implementation ("the experiments will be available soon", unchanged since 2021). No LICENSE file, so any future code there defaults to all rights reserved. Checked 2026-09-28 |
| Citation required under BY | Kayhan, O. S., Vredebregt, B., & van Gemert, J. C. (2021). *DelftBikes, data underlying the publication: Hallucination in Object Detection — A Study in Visual Part Verification* (Version 2) [Dataset]. 4TU.ResearchData. https://doi.org/10.4121/14866116 |

### BIKED

| | |
|---|---|
| Size | 4,512 processed designs × 2,395 parameters; 4,791 standardized designs from 4,800 downloaded; 4,510 designs compatible with the segmentation process |
| Origin | Rendered from BikeCAD parametric files, **not photographed**. Images are regenerated from parametric data with standardized colours, and with patterns and decals removed |
| Segmentation vocabulary | **Seven component groups**: five essential (frame, saddle, handlebars, wheels, cranks) and two nonessential (cargo racks, bottles). Semantic masks included. Exploded views are explicitly *not* included |
| Creators | Lyle Regenwetter, Brent Curry, Faez Ahmed — DeCoDE Lab, MIT Mechanical Engineering, with BikeCAD |
| Paper | Regenwetter, Curry & Ahmed (2021), *BIKED: A Dataset for Computational Bicycle Design with Machine Learning Benchmarks*, ASME J. Mech. Des. 144(3): 031706, doi 10.1115/1.4052585. Preprint arXiv:2103.05844v3 |
| Data hosting | Dropbox link from decode.mit.edu/projects/biked/; raw parametric data on Harvard Dataverse, doi:10.7910/DVN/GHQEDP |
| **Code licence** | **MIT**, Copyright (c) 2021 Lyleregenwetter. Verified in the repository LICENSE file on 2026-09-28. The README scopes it to the code and requests citation of the IDETC-21 paper |
| **Data licence** | **Not stated.** The project page, the GitHub repository and the paper were all checked on 2026-09-28; none specifies terms for the data itself. |
| Documented defects | §3.5 of the paper states that the 4,512 processed designs are a different subset of the original 4,800 than the 4,510 designs compatible with the segmentation process. The README adds that segmentation data is "to be updated to match model numbering", and that no example code uses the segmented component images |
| Documented biases | §6 of the paper records a bias toward BikeCAD default values, a temporal bias correlated with model number, no guarantee of design quality, designs the authors call "facetious or highly unrealistic", and a warning that raw data may contain offensive or proprietary imagery |

## Assessment against criterion 1 — identifying parts from a photograph

| | DelftBikes | BIKED |
|---|---|---|
| Imagery | Real photographs | CAD renders |
| Part vocabulary | 22 bike parts, named individually | 7 coarse component groups |
| Drivetrain represented | Yes: chain, gear case, front pedal, back pedal | Only "cranks", as one mask over the whole assembly |
| Brakes represented | Yes: front and back hand brake | No |
| Annotation type | Bounding boxes, the format our detector consumes | Semantic masks, requiring conversion |
| Handles missing and occluded parts | Yes, explicitly labelled | No |
| Reference code | None | None for the segmented images |

**DelftBikes wins this criterion decisively.** Its class list overlaps ours only in part. Of our eleven frozen classes, two match directly (`chain`, and `pedal` from its front and back pedal), two may match its hand brakes, and seven have no counterpart: there is no derailleur, cassette, crankset, bottom bracket or disc brake. The table is in ADR 0002. So DelftBikes supplies few labels we can use directly, but it is a genuine bike-part vocabulary annotated on real photographs in the format we need. That is what a pretraining stage requires.

**The task framing also matches ours more closely than the class list suggests.** The dataset was built to study a specific failure: detectors hallucinating parts that are not present. Figure 4 of the paper shows why — averaging the position and size of all 22 parts reproduces the outline of a bicycle, so detectors learn strong positional priors and then predict absent parts at their expected locations with high IoU. That is precisely the failure mode our Rule 2 ("no component claimed without a detection") exists to prevent. Adopting DelftBikes therefore gives us a published characterisation of the failure, an evaluation measure for it (the authors' recall-based Fvv score, weighting a hallucinated part ten times more costly than a missed one), and baseline numbers for three detectors.

**BIKED fails this criterion.** Renders rather than photographs, seven coarse groups with no brake component of any kind, a documented mismatch between its segmented and parametric subsets, and no reference code for the segmented images. Its strength is parametric design data, which is not what we need.

## Assessment against criterion 2 — legal usability

DelftBikes is **CC BY-SA 4.0**: usable for training with attribution, with the ShareAlike condition attaching only to distributed adaptations. That is acceptable and its consequences are recorded below.

BIKED's **code** is MIT. Its **data licence is stated nowhere** its authors publish. An unstated licence is not permission, and for a dataset we are otherwise rejecting it is not worth resolving.

## Assessment against criterion 3 — the 3D and augmented-reality extension

**Neither dataset supports 3D identification, and neither can be made to.**

DelftBikes is 2D boxes on 2D photographs. BIKED appears more promising because it derives from CAD, but BikeCAD produces parametric two-dimensional side-view drawings rather than 3D meshes: BIKED provides parameters and flat renders, not geometry that could be posed in space. Its paper confirms that exploded views — the nearest thing to a spatial decomposition — are not included in the dataset.

**The conclusion is that dataset selection is not the lever for the AR extension.** What determines whether this work extends to a headset is how we capture our own data, and that decision is being made now. Three capture requirements are therefore recorded here, because they cost almost nothing today and cannot be applied retroactively:

- **Multi-view capture.** Several angles per component instead of one canonical view. Needed for 2D robustness in any case, and it is the input format for later pose estimation or photogrammetry.
- **Capture metadata.** Approximate camera distance and angle, and the device used, recorded per image.
- **Video sweeps for a subset.** Frames yield a still dataset; the sweep additionally yields multi-view consistency at no extra capture cost.

A further point in DelftBikes' favour here is negative rather than positive: a headset's view is a close-up of a component, much closer to our own captures than to DelftBikes' side-on parked bicycles. This reinforces that DelftBikes is a pretraining aid and our own data is the target distribution — a distinction that holds for the AR extension as much as for the phone.

## Options considered

**A. Our own annotations only, from COCO-pretrained weights.** Simplest. Retained as the measured baseline.

**B. Pretrain on DelftBikes, then fine-tune on our annotations.** Real photographs, a genuine bike-part vocabulary, a compatible licence, and a task framing aligned with Rule 2.

**C. Pretrain on BIKED, then fine-tune.** Rejected: CAD renders, seven coarse groups with no brake component, documented subset misalignment, no reference code, no stated data licence.

**D. Pretrain on both.** Inherits every objection to C for no expected gain over B.

## Decision

**DelftBikes is adopted as a pretraining and auxiliary source. BIKED is rejected. Option A is retained as the baseline against which B must prove itself.**

DelftBikes is the better dataset on the criterion that matters most: identifying bicycle parts from a photograph. Ten thousand real photographs with 22 individually annotated bike parts — including chain, gear case, both pedals and both hand brakes — with per-part state labels and a permissive licence, is a stronger starting point than COCO weights alone.

Pretraining on DelftBikes and then fine-tuning on our own close-up annotations therefore becomes the plan of record rather than an optional experiment. The no-pretraining baseline (Option A) is still trained and measured on the same held-out split, so the benefit is demonstrated rather than assumed. If pretraining does not improve mAP@0.5, Option A stands and DelftBikes is dropped without cost.

BIKED is rejected on the evidence recorded above.

Neither dataset advances the AR extension. That option is protected instead by the capture requirements recorded in criterion 3, applied from the first capture session.

## Consequences

**Schedule and repository**

- T-201 (detector training) now has an upstream dependency on obtaining DelftBikes. This is a 507 MB download and no more, so the risk is low, but it is a dependency that did not previously exist and belongs on the board.
- **DelftBikes is never committed to the repository.** At 507 MB it would be unacceptable in Git regardless, and §9.6 forbids vendoring third-party corpora. It is fetched by a download script referencing DOI 10.4121/14866116, and the archive path is added to `.gitignore`.
- No code is reusable from the DelftBikes repository. Any data loader must be written by us, and its annotation format needs inspecting before T-201 is estimated.

**Licensing**

- Attribution is mandatory under CC BY-SA. The citation above goes in the final report, not only in this ADR.
- **If a DelftBikes-pretrained detector is ever published as a release artefact, the ShareAlike term must be resolved first**: either release those weights under CC BY-SA 4.0, or keep them internal. Weights trained only on our own annotations carry no such condition, which is one reason to keep the Option A baseline trained and available.

**Evaluation**

- **NFR-S4's target of 0.70 mAP@0.5 must be re-examined.** The DelftBikes paper reports that half of its 22 classes score under 20 % AP at IoU 0.5:0.95, that small parts such as bell and dynamo fall under 12 %, and that all classes except the wheels sit below 50 %; its overall AP50 is roughly 0.55. Those classes are generally larger and better represented than ours. Our target is therefore above what a published paper achieved on an easier version of this problem, and should be revised once the first detector is trained.
- **The paper's detector comparison is not evidence against YOLO.** Faster R-CNN and RetinaNet were fine-tuned from COCO-pretrained weights for 10 epochs, while YOLOv3 was trained from scratch for 200. YOLOv3 trailing reflects the training protocol as much as the architecture. A COCO-pretrained modern YOLO is a materially different starting point.
- **DelftBikes' absent-part boxes are not localisation ground truth.** The authors state as a limitation that annotations for non-existent parts are partly guesswork: the "most likely" box was recorded. Those boxes are usable for presence-and-absence work, not for measuring localisation accuracy.
- The authors' Fvv measure is worth adopting for our own hazard-relevant evaluation, since it formalises exactly our asymmetry: a part claimed but absent is more costly than a part missed.

**Capture**

- Our own capture sessions must produce multi-view images per component, recorded capture metadata, and video sweeps for a subset. These are required from the first session, not added later.

**Future**

- If the pretraining experiment fails to improve mAP, that outcome is recorded as a short amendment to this ADR rather than as a new one.
- No part-level 3D bicycle dataset is known to the team. If the AR extension is pursued seriously, it needs its own survey; this ADR does not cover it.

## Open items before this ADR moves to Accepted

1. BIKED data licence: check the Harvard Dataverse record at doi:10.7910/DVN/GHQEDP and record the outcome. If it too states nothing, record that with the date — an unstated licence is a complete finding.
2. ~~Class overlap: once the class list is frozen (#11), tabulate our 10–12 classes against DelftBikes' 22 so the relationship is checkable rather than asserted.~~ Done in ADR 0002 (2026-10-05): two direct matches, two possible, seven none.
3. NFR-S4: raise the target figure with the team in light of the published AP results, and either revise it or record why it stands.
4. Inspect DelftBikes' annotation format and confirm the conversion effort before T-201 is estimated.
5. Decision agreed by the team, and the draft wording replaced with what was decided, by whom, and when.

## References

- Issue #6 (T-308) — this survey
- Issue #11 (T-306) — frozen component class list; ADR 0002
- SDD-01 §8.1 — data sources · §8.2 and NFR-S4 — how detection is measured · §9.6 — repository policy on large files and third-party corpora
- Kayhan, O. S., Vredebregt, B., & van Gemert, J. C. (2021). *DelftBikes, data underlying the publication: Hallucination in Object Detection — A Study in Visual Part Verification* (Version 2) [Dataset]. 4TU.ResearchData. https://doi.org/10.4121/14866116
- Kayhan, O. S., Vredebregt, B., & van Gemert, J. C. (2021). Hallucination in Object Detection: A Study in Visual Part Verification. *IEEE ICIP 2021*. arXiv:2106.02523
- Regenwetter, L., Curry, B., & Ahmed, F. (2021). BIKED: A Dataset for Computational Bicycle Design with Machine Learning Benchmarks. *ASME Journal of Mechanical Design*, 144(3), 031706. https://doi.org/10.1115/1.4052585