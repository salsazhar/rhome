# Rhome — Research and Parameter Validation Summary

**Version:** 0.4  
**Date:** 23 August 2026  
**Status:** Canonical scientific-validation record

## 1. Purpose

This document records the evidence used to constrain the first Rhome model and synthetic-data generator.

It has two functions:

1. provide an auditable scientific basis for model structure and numerical priors; and
2. prevent later implementation choices from acquiring a false aura of scientific certainty merely because they have been encoded in software.

Rhome is not attempting to derive every coefficient directly from published literature. In several areas the literature establishes **direction, plausible timescale or population distribution**, but does not identify the exact coefficient required by a computational state-space model. In those cases Rhome uses a transparent **evidence-constrained engineering prior** and labels it accordingly.

## 2. Evidence grades used in this document

### Grade A — strong constraint

Systematic review, meta-analysis, large meta-regression, major validation study or convergent body of evidence that directly addresses the model quantity.

### Grade B — moderate constraint

Controlled acute study, smaller validation study or consistent mechanistic evidence that constrains direction/timescale but does not determine a universal parameter.

### Grade C — engineering prior

A number or functional form required to make the model explicit but not directly identifiable from available evidence. Grade C does **not** mean arbitrary: the prior must remain compatible with Grade A/B evidence and must be calibratable.

## 3. Executive conclusions

The research supports the following modelling decisions.

1. **RPE/RIR is usable but noisy.** The resistance-training RPE scale explicitly maps RPE 10 to 0 RIR and RPE 9 to approximately 1 RIR (Zourdos et al., 2016). Trained lifters can estimate low RIR reasonably well, but errors around one repetition are normal (Refalo et al., 2024). Therefore Rhome should use RPE/RIR, while modelling observation error rather than treating it as ground truth.

2. **REPS–%1RM is a distribution, not a universal conversion equation.** A large meta-regression of 952 repetitions-to-failure tests from 7,289 individuals shows substantial between-person variation and material exercise effects, especially for bench press and leg press (Nuzzo et al., 2024). Therefore Rhome should use a lookup/interpolation with uncertainty rather than a single universal Epley equation.

3. **Proximity to failure matters more clearly for hypertrophy than for strength.** Meta-regression suggests hypertrophy tends to increase as sets terminate closer to failure, while strength gains appear much less sensitive across a broad RIR range; the precise continuous relationship remains uncertain (Robinson et al., 2024). Therefore Rhome may use a monotonic stimulus multiplier but should label exact coefficients as priors.

4. **Failure is disproportionately fatiguing.** Controlled resistance-training studies show that training to failure produces a greater acute decrement and can slow recovery for approximately 24–48 h compared with non-failure work, even under matched-volume comparisons (Morán-Navarro et al., 2017). Therefore the fatigue multiplier near 0 RIR should rise more sharply than the stimulus multiplier.

5. **Recovery from demanding resistance work commonly spans one to three days, but there is no universal muscle-recovery clock.** Heavy repeated resistance work can leave neuromuscular performance measures depressed for 48–72 h (Thomas et al., 2018), while the exact time course depends on volume, effort, exercise and individual response. Therefore a 24–42 h local-fatigue half-life is a modelling prior chosen to reproduce a plausible 48–72 h residual tail, not an empirical half-life measured from tissue.

6. **“CNS fatigue” would overclaim.** Heavy resistance, sprint and jump training can produce fatigue lasting up to 72 h, but Thomas et al. found that this was not primarily explained by decrements in CNS function (Thomas et al., 2018). Rhome should therefore expose **Neuromuscular Strain**, not “CNS load”.

7. **Weekly volume has diminishing returns and indirect sets matter.** A 2026 meta-regression across 67 studies found positive volume relationships for hypertrophy and strength with diminishing returns, and the strongest evidence for quantifying an indirect set as approximately half a direct set (Pelland et al., 2026). This directly supports Rhome's 1.0/0.5 primary/secondary stimulus convention as a population prior.

8. **Load and volume should not be conflated.** Large network meta-analysis indicates that higher loads are particularly important for maximising 1RM strength, whereas a wide range of resistance-training prescriptions can promote hypertrophy and multiple sets are important (Currier et al., 2023). Therefore Rhome should separate muscular stimulus from heavy-load neuromuscular/strength-specific stress.

9. **Sleep matters, but a single deterministic sleep penalty would be poor modelling.** A meta-analysis of 69 publications found an overall negative effect of acute sleep loss on exercise performance, but with very high heterogeneity and dependence on protocol and time of day (Craven et al., 2022). Sleep should therefore make modest probabilistic/contextual contributions to recovery and performance rather than act as an on/off readiness gate.

10. **HRV is useful in context, not as a solitary truth signal.** Meta-analysis of autonomic measures shows that vagal HRV can change with both positive adaptation and maladaptation, and interpretation requires additional measures (Bellenger et al., 2016). Rhome should use rolling personal baselines and combine HRV with resting HR, sleep and temperature rather than reacting strongly to one nightly reading.

11. **Nightly Oura HR/RMSSD and global sleep measures are defensible inputs.** Oura nocturnal HR and RMSSD have shown good agreement with ECG, particularly when aggregated over the night (Cao et al., 2022). Oura Gen3 has also shown good agreement with polysomnography for several global sleep measures, while some staging/efficiency error remains (Svensson et al., 2024). The simulator should therefore add measurement noise and the engine should prefer night-level trends over false precision.

12. **Fitness–fatigue impulse-response models are a useful scaffold, not a proven physiological truth.** The literature supports the conceptual use of antagonistic fast-fatigue and slow-fitness responses, but also documents limited predictive performance and oversimplification of multivariate physiology (Imbach et al., 2022). Rhome may borrow the dynamical structure while remaining multivariate and personalised.

13. **Do not use ACWR as an injury-risk engine.** A critical analysis concluded there is no evidence supporting use of the acute:chronic workload ratio for training recommendations intended to reduce injury risk, and detailed substantial statistical/conceptual problems (Impellizzeri et al., 2020). Rhome should show short- and long-term load traces separately rather than use a “safe zone”.

---

# 4. Resistance-training effort: RPE and RIR

## 4.1 Scientific evidence

Zourdos et al. introduced and evaluated a resistance-training-specific RPE scale explicitly tied to repetitions in reserve: RPE 10 corresponds to 0 RIR, RPE 9 to 1 RIR, and so forth (Zourdos et al., 2016). This makes RPE/RIR particularly suitable for Rhome because the variable is already logged at the set level and captures information that raw tonnage cannot.

However, RIR is subjective. In resistance-trained men and women performing bench press, Refalo et al. reported a mean raw RIR error of approximately −0.17 repetitions and a mean absolute error of 0.65 repetitions, with substantial spread around those means (Refalo et al., 2024). Accuracy also varies with exercise, load, familiarity and distance from failure.

**Evidence grade:** A for the RPE/RIR convention; B for the magnitude of observation noise.

## 4.2 Rhome decision

If explicit RIR is unavailable:

$$
\mathrm{RIR}=\max(0,10-\mathrm{RPE}).
$$

For the simulator, true RIR is corrupted before being logged:

$$
\epsilon_{RIR}\sim N(0,0.9^2)\text{ reps},
$$

clipped to a plausible range.

The 0.9-repetition SD is intentionally a little broader than the cited bench-press study because the synthetic dataset contains multiple exercises and rep ranges.

**Parameter status:** Grade C, constrained by Grade B evidence.

---

# 5. Repetitions to failure and percentage of 1RM

## 5.1 Scientific evidence

Nuzzo et al. (2024) performed a meta-regression using 952 repetitions-to-failure tests from 269 studies, representing 7,289 individuals. The analysis explicitly quantified both mean repetitions and between-individual variation at given percentages of 1RM. Sex, age and training status were not strong moderators, but exercise was: leg press permitted more repetitions than bench press across the loading spectrum (Nuzzo et al., 2024).

This matters for Rhome because a set such as `80 kg × 8 @ RPE 9` contains an implicit statement about relative intensity. If one repetition was probably left in reserve, the set implies roughly a 9RM load; the Nuzzo relationship is a better population prior for that inference than an old deterministic “reps = fixed %1RM” chart.

Selected general-model means reported by Nuzzo et al. are:

| %1RM | Mean repetitions to failure |
|---:|---:|
| 95 | 3.28 |
| 90 | 4.94 |
| 85 | 7.15 |
| 80 | 9.75 |
| 75 | 12.37 |
| 70 | 14.80 |
| 65 | 17.11 |
| 60 | 19.53 |
| 55 | 22.43 |
| 50 | 25.99 |

The same paper provides exercise-specific curves for bench press and leg press (Nuzzo et al., 2024).

**Evidence grade:** A.

## 5.2 Rhome decision

1. Compute implied repetitions to failure: `reps + RIR`.
2. Invert the Nuzzo lookup using piecewise-linear interpolation.
3. Use exercise-specific curves for bench press and leg press.
4. Use the general curve for other exercises in v0.
5. Handle the two ends of the domain differently, and flag confidence in both cases.

Longitudinally, Rhome should learn exercise-specific deviations for the individual athlete.

## 5.3 Behaviour outside the tabulated domain

The reported relationship covers roughly 3.3 to 26 repetitions to failure, or 50–95% of 1RM. Sets fall outside it in both directions, and the two directions warrant different treatment.

**Above 95% (fewer than ~3.3 repetitions to failure).** Simple clipping would make a true single indistinguishable from a heavy triple and would prevent the model from ever recording 100% of 1RM — a problem, since low-fatigue singles are among the most informative capacity anchors available. Rhome therefore extends the curve linearly to the point (1 repetition, 100% 1RM).

That anchor is not an empirical estimate requiring evidential support: one repetition performed at maximum *is* 100% of 1RM by the definition of 1RM. What is a prior is the linear shape of the short segment joining the anchor to the tabulated curve, and sets in this region carry reduced confidence accordingly.

**Below 50% (more than ~26 repetitions to failure).** Here the relationship genuinely flattens and between-individual variation grows large. Nuzzo et al. report increasing dispersion at lower relative loads, so extrapolation would manufacture precision that the data do not contain. Rhome clips at 50% and marks the set as low-confidence, which excludes it from performance estimation while retaining its full contribution to the fatigue channels.

**Evidence grade:** A for the tabulated interior; C for the near-maximal extension; the high-repetition clip is a refusal to extrapolate rather than a parameter.

---

# 6. Proximity to failure as stimulus

## 6.1 Scientific evidence

Robinson et al. (2024) synthesised resistance-training studies using estimated RIR as a continuous predictor. Their best-fitting hypertrophy models indicated greater muscle-size gains as sets were terminated closer to failure. By contrast, the relationship between RIR and strength gain was negligible across the analysed range. Crucially, the authors described the work as exploratory and cautioned that the exact dose-response remains uncertain because RIR often had to be estimated from intervention descriptions (Robinson et al., 2024).

This is sufficient to justify a monotonic proximity-to-failure term. It is **not** sufficient to claim that, for example, a 2-RIR set has exactly 85% of the hypertrophic stimulus of a failure set.

**Evidence grade:** A for direction; C for exact numerical mapping.

## 6.2 Rhome v0 prior

| RIR | Stimulus multiplier |
|---:|---:|
| 0 | 1.00 |
| 1 | 0.95 |
| 2 | 0.85 |
| 3 | 0.72 |
| 4 | 0.58 |
| 5 | 0.45 |
| 6+ | 0.30 |

These values are deliberately versioned as `prior_proximity_stimulus_v0.1`. They should later be sensitivity-tested and personalised.

---

# 7. Volume, fractional sets and diminishing returns

## 7.1 Scientific evidence

Pelland et al. (2026) analysed 67 studies with 2,058 participants and modelled weekly volume/frequency dose-response relationships for strength and hypertrophy. Before meta-regression, they classified sets as direct or indirect and compared several counting methods. The strongest evidence favoured the **fractional method**, in which an indirect set counts as 0.5 of a direct set. Greater volume was associated with greater strength and hypertrophy gains, but the best-fit relationships showed diminishing returns; the diminishing returns were especially pronounced for strength (Pelland et al., 2026).

The finding is unusually useful for Rhome because it maps directly onto an exercise-to-muscle contribution matrix.

**Evidence grade:** A for fractional counting as an adaptation-volume prior and for diminishing returns.

## 7.2 Rhome decision

Stimulus contribution:

- primary/direct muscle: 1.0;
- secondary/indirect muscle: 0.5;
- stabiliser: 0 for adaptation-set counting.

For acute fatigue, the same 1.0/0.5 convention is provisionally used for primary/secondary muscles, while stabilisers may receive a small fatigue coefficient (0.20). The stabiliser coefficient is an engineering prior, not a direct interpretation of the Pelland analysis.

Rhome will retain **raw effective set/stimulus load** and apply a separate concave transform for adaptation displays, rather than pretending that the 18th weekly set has identical marginal adaptation to the first few sets.

---

# 8. External load: hypertrophy versus strength

## 8.1 Scientific evidence

The largest Bayesian network meta-analysis of resistance-training prescription located 178 strength studies and 119 hypertrophy studies. All examined resistance-training prescriptions improved strength and hypertrophy compared with no exercise. Higher-load prescriptions (greater than approximately 80% 1RM in that classification) ranked highest for strength, whereas multiple sets were a prominent feature of the highest-ranked hypertrophy prescriptions and a broad range of prescriptions produced hypertrophy (Currier et al., 2023).

This argues against a model in which “hard set = hard set” for every purpose. A hard set can be muscularly stimulative while differing substantially in high-force/strength-specific demand.

**Evidence grade:** A.

## 8.2 Rhome decision

Rhome separates:

- muscular adaptive stimulus;
- local fatigue;
- high-force neuromuscular strain;
- systemic cost.

Relative intensity enters the neuromuscular channel more strongly than the muscular-stimulus channel. This is consistent with the evidence but the exact mathematical exponent (`relative_intensity²` in v0) is a Grade C engineering choice.

---

# 9. Fatigue and recovery after resistance training

## 9.1 Failure versus non-failure

Morán-Navarro et al. (2017) compared resistance-training protocols including 3×5(10), 6×5(10) and 3×10(10) in bench press and squat. The failure protocol produced a larger acute performance decrement and slower recovery than non-failure protocols; importantly, the comparison with 6×5(10) showed that this could occur even when total repetition volume was matched. The authors reported slower recovery over roughly the subsequent 24–48 h after failure training (Morán-Navarro et al., 2017).

**Evidence grade:** B, with strong direct relevance.

## 9.2 Heavy repeated effort and the 48–72 h tail

Thomas et al. (2018) studied heavy resistance (10×5 back squats at 80% 1RM), jump and sprint sessions. Fatigue resolved by 48–72 h depending on condition; muscle-function decrements persisted to 48 h after all conditions and voluntary-activation changes could persist for 24–48 h. Yet the overall fatigue was **not primarily underpinned by CNS decrements** (Thomas et al., 2018).

This provides a strong reason to preserve a multi-day fatigue tail after demanding sessions, but it does not identify a universal exponential half-life.

**Evidence grade:** B.

## 9.3 Rhome v0 fatigue priors

### Local fatigue half-life

- mean: 30 h;
- per-muscle simulator range: approximately 24–42 h.

### Neuromuscular strain half-life

- 24 h.

### Systemic fatigue half-life

- 30 h.

These are **Grade C evidence-constrained priors**. They are selected so that large impulses retain meaningful residual state at 48–72 h. They should later be inferred per athlete and per muscle from performance recovery.

## 9.4 Failure-fatigue multiplier

Rhome v0 uses:

| RIR | Fatigue multiplier |
|---:|---:|
| 0 | 1.35 |
| 1 | 1.15 |
| 2 | 1.00 |
| 3 | 0.90 |
| 4 | 0.82 |
| 5+ | 0.75 |

The shape is consistent with the disproportionate fatigue of failure training demonstrated by Morán-Navarro et al. (2017), but the exact values are Grade C.

---

# 10. Why Rhome uses “Neuromuscular Strain”, not “CNS fatigue”

The consumer-fitness language of “CNS fatigue” suggests a specificity the available inputs cannot provide. Rhome has no direct transcranial stimulation, voluntary activation, evoked twitch or other laboratory measure that could partition central from peripheral mechanisms.

Thomas et al. (2018) is especially instructive: demanding maximal-effort training produced fatigue that could require up to 72 h to resolve, yet the investigators concluded that the fatigue was not primarily attributable to decrements in CNS function.

Accordingly:

- Rhome **can** construct an operational index of repeated high-force/high-relative-intensity work;
- Rhome **cannot** claim that this index measures the CNS;
- the user-facing term is **Neuromuscular Strain**;
- its scientific status is an interpretable load proxy.

**Evidence grade:** B for the claim boundary; C for the numerical index.

---

# 11. Sleep and training performance

## 11.1 Scientific evidence

Craven et al. (2022) meta-analysed 69 publications and 227 performance outcomes comparing normal sleep with acute sleep loss (≤6 h in 24 h). Across exercise categories, acute sleep loss was associated with an average performance decrement of approximately 7.6%, but heterogeneity was extremely high (`I² ≈ 98%`). Effects varied with the sleep-loss protocol and time of day; deprivation and late restriction were particularly detrimental, while morning performance was often less affected than afternoon/evening performance (Craven et al., 2022).

The correct conclusion for Rhome is not “6 hours of sleep = −7.6% strength.” The correct conclusion is that sleep loss changes the probability distribution of next-day performance and perceived effort.

**Evidence grade:** A for the existence/direction of an effect; C for an individual nightly coefficient.

## 11.2 Rhome decision

Sleep contributes to the **Recovery Context** multiplier through a modest bounded term.

For synthetic Athlete A:

- target/reference sleep = 7.5 h;
- the sleep contribution is scaled in roughly one-hour units;
- recovery-context effects are bounded so that one poor night cannot halve estimated recovery speed;
- deliberate 5–6 h sleep-restriction scenarios add probabilistic performance/RPE impairment in the simulator.

The simulator should preserve heterogeneity: some short-sleep sessions will still perform well.

---

# 12. HRV and resting heart rate

## 12.1 Scientific evidence

Bellenger et al. (2016) reviewed and meta-analysed autonomic heart-rate measures in trained athletes. Positive training adaptation was often accompanied by increases in vagally mediated HRV indices such as RMSSD; however, autonomic patterns under overreaching were not uniquely directional. The review therefore supports HRV as a monitoring signal while arguing against simplistic interpretation in isolation (Bellenger et al., 2016).

This is directly relevant to Rhome. A low HRV night can reflect training load, sleep disturbance, stress, illness, measurement variation or other factors. Conversely, a high HRV value is not proof that all systems are fully recovered.

**Evidence grade:** A for contextual use; weak for any universal threshold.

## 12.2 Conditioning the expectation on recent training

A rolling personal baseline answers "is this reading unusual for you?". It cannot answer the more useful question, which is "is this reading unusual *given what you did yesterday*?".

The distinction is not academic. Under a plain rolling baseline, a depressed RMSSD after a heavy session and a depressed RMSSD on a rest day are identical evidence, and the model reacts to both the same way. One is the expected consequence of training the model already knows about; the other is information about something it cannot see.

Rhome therefore conditions the autonomic expectation on its own systemic-fatigue estimate and uses the residual. Bellenger et al. support the direction — vagal indices move with accumulated load — while providing no basis for a coefficient, so the two constants involved are Grade C and deliberately modest.

**The expectation is not a forecast, and Rhome does not predict wearable data.** Its accuracy is not the object. Nocturnal HRV responds to work stress, alcohol, illness and sleep timing far more than to training, and a model scored on predicting it would be scored mostly on its ability to predict things outside the training system — creating pressure to model life events in pursuit of a number no athlete wants. The expectation exists to *partition* the reading into the part recent training accounts for and the part it does not. The residual is the useful quantity, precisely because it is what the training model cannot explain.

A consequence follows for confidence: persistent unexplained deviation means the model is missing something it cannot name, and should report reduced confidence rather than folding the surprise into the recovery multiplier as though it were understood.

**Evidence grade:** A for the direction of autonomic response to accumulated load; C for the coefficients.

## 12.3 Rhome decision

1. Use **log RMSSD**, not raw HRV alone, for baseline-standardised modelling.
2. Interpret HRV against a rolling personal baseline.
3. Combine it with resting HR, sleep and temperature.
4. Clip z-scores to reduce the influence of outliers.
5. Use modest coefficients.
6. Do not let one anomalous nightly value dominate local-muscle fatigue estimates.

v0 recovery formula:

$$
\rho_t=\mathrm{clip}\left(
1+0.05z_{HRV}-0.04z_{RHR}+0.04z_{sleep}+0.02z_{eff}-0.03|z_T|,
0.80,1.15
\right).
$$

Every coefficient in this expression is **Grade C**. The scientific basis lies in using these variables jointly and relative to baseline, not in the exact weights.

---

# 13. Oura as a measurement source

## 13.1 HR and HRV

Cao et al. (2022) compared Oura nocturnal HR/HRV with a medical-grade ECG in free-living overnight monitoring. HR and RMSSD showed high agreement/correlation, and averaging over the whole night reduced error variance compared with short five-minute segments (Cao et al., 2022).

This supports using nightly Oura RMSSD and resting/nocturnal HR as Rhome inputs.

## 13.2 Sleep

Svensson et al. (2024) compared Oura Gen3 sleep staging with multi-night ambulatory polysomnography in 96 participants contributing more than 421,000 30-second epochs. Oura showed good agreement for several global sleep measures; small systematic differences remained in sleep efficiency and REM duration, and stage-level classification was not perfect (Svensson et al., 2024).

This supports using total sleep time and sleep efficiency as contextual data while modelling measurement error and avoiding excessive dependence on specific sleep stages.

## 13.3 Rhome simulator measurement noise

Provisional wearable noise:

- RMSSD multiplicative error: ~5–7% scale;
- resting HR error: ~0.5–1 bpm SD;
- total-sleep measurement error: ~10–15 min SD;
- sleep-efficiency error: ~1–2 percentage points SD.

These values are **Grade C approximations inspired by validation performance**, not a fitted error model for a particular Oura generation/firmware. They exist to stop synthetic data from being unrealistically clean.

---

# 14. Fitness–fatigue modelling

## 14.1 Scientific background

Fitness–fatigue impulse-response models represent training as producing antagonistic responses with different decay rates: a slower positive “fitness” component and a faster negative “fatigue” component. This mathematical form is attractive because it naturally produces taper/deload phenomena and allows time-continuous projection.

However, Imbach et al. (2022) reviewed conceptual issues in these models and noted that their prediction performance remains mixed, partly because they simplify complex physiology and often treat performance as a univariate response to a univariate training impulse (Imbach et al., 2022).

**Evidence grade:** A for the existence/limitations of the framework; C for Rhome's resistance-training parameterisation.

## 14.2 Rhome decision

Rhome borrows the **dynamical idea**, not the claim that a classical Banister model is biologically complete.

Rhome is multivariate:

- separate muscle fatigue states;
- systemic fatigue;
- neuromuscular strain;
- slow adaptive state;
- exercise-specific performance;
- recovery-context modulation.

A 42-day slow adaptation time constant is used in v0 as a broad engineering starting point. It is **not** presented as a validated resistance-training muscle-adaptation constant and should become athlete-specific.

## 14.3 Coupling fatigue to expressed performance

The model converts latent fatigue into an expected performance decrement through three coefficients ($\lambda_F$, $\lambda_N$, $\lambda_G$). No published study identifies these values, because no published study works in the units of this model. They are therefore Grade C. What the literature does constrain is the *magnitude of decrement they should produce*.

Morán-Navarro et al. (2017) and Thomas et al. (2018) both report substantial acute decrements after demanding protocols, with meaningful residual impairment persisting 24–48 h and, in some measures, to 72 h. Those are the relevant anchors, with one important qualification: the largest reported decrements are measured minutes to hours after the final set, whereas Rhome's quantity predicts performance in a *subsequent training session*, typically at least 24 h later. Calibrating $\lambda$ against immediate post-exercise decrements would substantially overstate next-session suppression.

The v0.2 values are therefore set to reproduce the following behaviour, which is checked as an acceptance test rather than asserted. These bands were obtained by evaluating the model equations over representative sessions, not estimated by eye:

| State, evaluated 24 h after the most recent session | Suppression |
|---|---|
| Fresh; after a deload week | < 1.5% |
| One ordinary hard session | 4–6% |
| One failure-heavy session | 5–7% |
| Within an ordinary training week (two sessions in 72 h) | 6–8% |
| Within a failure-heavy block | 8–10% |
| Peak of a deliberate overload block | 13–16% |

The failure-versus-ordinary **ordering** is the part of this table with the clearest evidential support: Morán-Navarro et al. demonstrated slower recovery after failure protocols even at matched volume.

The *size* of that gap deserves an explicit caveat. For a single session it is only one to two percentage points, because the entire effect is carried by the failure-fatigue multiplier ratio of 1.35. It would be easy to widen the gap by inflating that multiplier until the performance difference looked more impressive, and that temptation should be resisted: the evidence constrains the direction and the disproportionality of the acute fatigue response, not a specific next-session performance separation. The gap does widen under accumulation, which is the behaviour the studies describe.

**Revision from v0.1.** The original coefficients (0.030, 0.020, 0.015) produced roughly 2.4% suppression in the ordinary-session case. That is small relative to the day-to-day performance variation a real athlete exhibits, which would have left the fatigue states weakly identifiable from observed performance — the model would have been internally consistent but empirically inert. The v0.2 values are approximately 2.2× larger. This was a calibration correction, not new evidence, and the coefficients remain Grade C and first in line for personalisation.

**Evidence grade:** B for the existence and rough timescale of the decrement; C for the coefficients.

## 14.4 Why the adaptation state does not drive capacity in v0

Rhome maintains a slow adaptive state per muscle, but in v0 it does **not** feed the performance model. Estimated capacity is driven by observed performance alone.

This is a deliberate epistemic choice rather than an oversight. Coupling the two requires an adaptation-gain parameter converting effective sets into strength, and nothing in the reviewed literature identifies such a parameter for resistance training. Pelland et al. (2026) establish that more volume is associated with more gain *with diminishing returns*, across studies and populations — which constrains a group-level dose-response curve, not an individual's week-to-week capacity update.

Imposing a gain anyway would produce a model that reports the athlete is stronger because they performed more sets, in the absence of any evidence that they lifted more. That is precisely the overreach Imbach et al. (2022) identify in first-order fitness–fatigue models: an appealing dynamical form standing in for physiology it does not actually capture.

The separation is itself a testable claim. If the adaptation state carries no predictive information about capacity beyond what recent observed performance already contains, v0 loses nothing by excluding it. Answering that question empirically is a Phase-3 objective.

**Evidence grade:** A for diminishing returns at the population level; the absence of an identified individual gain parameter is the reason for the decision.

---

# 15. Acute versus chronic load and ACWR

Impellizzeri et al. (2020) argued that the acute:chronic workload ratio has conceptual, causal and statistical problems and concluded that evidence does not support using ACWR-based manipulation to reduce injury risk. Ratio construction itself can introduce artifacts and ambiguous interpretation (Impellizzeri et al., 2020).

Rhome will therefore not display:

- “safe” 0.8–1.3 zones;
- injury-risk percentages derived from ACWR;
- recommendations to raise/lower training solely to keep a ratio within a band.

Rhome **may** maintain:

- a short exponentially weighted load trace (v0: ~7 d time constant/window convention);
- a slow training-capacity/load trace (v0: ~42 d convention).

These are shown independently as descriptive state variables.

**Evidence grade:** A for rejecting causal ACWR injury claims; C for exact Rhome EWMA time constants.

---

# 16. Parameter validation register

| Model component | Rhome v0 choice | Evidence | Grade | Interpretation |
|---|---|---|---|---|
| RPE→RIR | 10→0, 9→1, etc. | Zourdos et al. (2016) | A | Established RT-specific convention |
| RIR logging noise | SD 0.9 reps | Refalo et al. (2024) | B/C | Conservative multi-exercise simulator prior |
| REPS→%1RM | Nuzzo lookup/interpolation | Nuzzo et al. (2024) | A | Population prior with exercise-specific exceptions |
| Primary stimulus weight | 1.0 | Definition/reference | C | Unit reference |
| Secondary stimulus weight | 0.5 | Pelland et al. (2026) | A/B | Strongly motivated fractional-set prior |
| Stabiliser stimulus | 0 | Scope decision | C | Avoid pretending stabilisation equals hypertrophy set |
| Stabiliser fatigue | 0.20 | None direct | C | Small fatigue-spillover prior |
| RIR stimulus curve | 1.00→0.30 from 0→6+ RIR | Robinson et al. (2024) | A/C | Direction supported; exact curve provisional |
| Failure fatigue | 1.35 at 0 RIR | Morán-Navarro et al. (2017) | B/C | Disproportionate fatigue supported; magnitude provisional |
| Local fatigue half-life | 24–42 h; mean 30 h | Morán-Navarro et al. (2017); Thomas et al. (2018) | B/C | Chosen to yield realistic 48–72 h tail |
| Neuromuscular strain half-life | 24 h | Thomas et al. (2018) | B/C | Operational, not CNS measurement |
| Systemic fatigue half-life | 30 h | Broad recovery evidence | C | Provisional |
| Neuromuscular load dependence | relative intensity² × compoundness | Currier et al. (2023) provides direction | A/C | High loads matter for strength; exponent is engineering |
| Recovery inputs | HRV, RHR, sleep, efficiency, temperature | Bellenger et al. (2016); Craven et al. (2022) | A | Joint contextual variables |
| Recovery coefficient bounds | 0.80–1.15 | no direct universal mapping | C | Deliberately conservative |
| Oura HR/RMSSD use | nightly aggregates | Cao et al. (2022) | B | Valid enough for contextual monitoring |
| Oura sleep use | TST/efficiency mainly | Svensson et al. (2024) | B | Global measures preferred over stage precision |
| Slow adaptation $\tau$ | 42 d | fitness–fatigue framework | C | Starting value only |
| Adaptation gain $k_A$ | 0.014 | none direct | C | Normalisation: A ≈ 1 at 12 sets/week |
| Adaptation → capacity link | none in v0 | Pelland et al. (2026); Imbach et al. (2022) | A/C | Individual gain unidentified; deliberate omission |
| Near-maximal %1RM extension | linear to (1 rep, 100%) | definition of 1RM | A/C | Anchor definitional; joining segment is a prior |
| High-rep %1RM clip | 50%, no extrapolation | Nuzzo et al. (2024) domain | A | Refusal to extrapolate, not a parameter |
| $\lambda_F$, $\lambda_N$, $\lambda_G$ | 0.065, 0.045, 0.030 | Morán-Navarro (2017); Thomas (2018) | B/C | Calibrated to next-session decrement bands |
| Suppression clip | 0.25 in exponent | none | C | Numerical guard, not a physiological bound |
| Performance weights $\omega$ | $c^F$ normalised to sum 1 | none direct | C | Stabilisers included: they limit expression |
| Capacity update | Huber $c$ = 0.10, $\alpha$ = 0.06 | none direct | C | Chosen for single-session robustness |
| Bodyweight fractions $\beta$ | 1.00 / 0.95 / 0.65 / 0.55 / 0.85 | segmental mass | C | Gross anatomical prior, not force-plate data |
| Drop-set performance use | excluded | Nuzzo assumption | B | Inversion assumes a non-pre-fatigued set |
| Confidence index | multiplicative, per channel | none | C | Evidence sufficiency, explicitly not a probability |
| Autonomic expectation γ | 0.30 HRV, 0.25 RHR | Bellenger et al. (2016) | A/C | Direction supported; coefficients are priors |
| Wearables as model outputs | not predicted | Bellenger et al. (2016) | A | Autonomic variance is largely non-training; predicting it would score the wrong thing |
| Unexplained-deviation penalty | C_explain, floor 0.6 | none | C | Confidence consequence only; never alters ρ |
| Muscle model groups | 16, coarser than display | Pelland et al. (2026); volume literature | A | Evidence is reported per muscle group, never per region |
| Regional muscle states | not modelled | no supporting evidence | A | Upper vs lower chest fatigue is not a claim the evidence licenses |
| Muscle mass weights μ | table in MODEL §derived | segmental anatomy | C | Modulates derived systemic cost; does not drive it |
| Derived κ, b | from equipment, pattern, tags | none direct | C | Engineering derivation; validated against documented class bands |
| Derived-coefficient penalty | ξ = 0.75 | none | C | Reduces confidence only; never alters the dose |
| Non-repetition exercise kinds | recorded, excluded | Nuzzo et al. (2024) domain | A | Relative intensity is defined on repetitions |
| ACWR injury ratio | not used | Impellizzeri et al. (2020) | A | Explicit product constraint |

---

# 17. Claim boundaries

These boundaries are part of the scientific specification and should be preserved in product copy.

## Rhome may say

- “Estimated local fatigue is elevated.”
- “This session produced high neuromuscular strain in the model.”
- “Your recent sleep/HRV/RHR context is less favourable than baseline.”
- “Projected fatigue is expected to decline over the next 48 hours if no further training occurs.”
- “Observed performance is below your recent trend.”
- “The model is becoming more/less confident as longitudinal data accumulate.”

## Rhome should not say

- “Your CNS is 72% fatigued.”
- “Your chest is exactly 64% recovered biologically.”
- “An HRV of X means you should not train.”
- “Your ACWR is 1.4, therefore injury risk is high.”
- “You are overtrained.”
- “Your wearable proves you are ill.”

Rhome is a training-state inference tool, not a diagnostic device.

---

# 18. What the research does not yet validate

The literature reviewed here does **not** directly determine:

- exact muscle-specific recovery half-lives;
- exact exercise-to-muscle contribution coefficients for every movement;
- exact local-fatigue units per set;
- exact systemic cost of a squat versus a row;
- exact sensitivity of an individual's performance to HRV or sleep deviations;
- an exact mapping from a latent fatigue score to a perceived “recovery percentage”;
- the optimal adaptation time constant for resistance training;
- the personalised effect of high daily step counts on lower-body recovery.

These quantities are therefore either simulator parameters or inference priors. The correct scientific progression is:

1. constrain them with plausible literature-backed ranges;
2. test model identifiability on synthetic data;
3. collect real longitudinal data;
4. estimate athlete-specific parameters with uncertainty;
5. revise the priors when the evidence or data justify doing so.

---

# 19. Research-backed v0 decisions to freeze

For model version 0.1, the following are now frozen unless a later documented revision supersedes them:

1. Use `RIR = 10 − RPE` when explicit RIR is absent.
2. Model RIR as noisy.
3. Estimate relative intensity using the Nuzzo REPS–%1RM relationship rather than a single Epley formula.
4. Count direct muscular stimulus at 1.0 and indirect at 0.5.
5. Separate muscular stimulus, local fatigue, neuromuscular strain and systemic fatigue.
6. Give failure/near-failure work a disproportionately larger fatigue cost.
7. Use exponential decay for v0 fatigue dynamics, with half-lives as priors rather than biological facts.
8. Use “Neuromuscular Strain”, never “CNS fatigue”, in the product.
9. Use underlying wearable variables rather than Oura Readiness as the v0 recovery driver.
10. Standardise HRV/RHR relative to personal rolling baselines.
11. Make the recovery modifier conservative and bounded.
12. Treat steps as low-grade activity load, not resistance volume.
13. Keep short/long load traces separate and do not use ACWR injury safe zones.
14. Keep the simulator structurally richer than the inference model.
15. Label all unvalidated exact coefficients in code/config as priors.
16. Model training dose as a function of relative effort, not absolute external load. Absolute load informs the performance channel only.
17. Extend the relative-intensity mapping to the definitional point (1 repetition, 100% of 1RM) rather than clipping; refuse to extrapolate below 50%; flag confidence at both ends.
18. Do not couple the slow adaptation state to estimated capacity in v0. Capacity moves on observed performance alone.
19. Update capacity with a bounded-influence (Huber) rule, so that no single session can move it materially.
20. Exclude drop-set segments and clipped high-repetition sets from performance estimation while retaining their full fatigue contribution.
21. Report confidence per channel rather than as one global scalar, and always display the binding reason alongside it.
22. Make every displayed state expandable into an exact impulse decomposition together with the versioned parameters it depends on.
23. Anchor recovery-context windows to the sleep episode rather than the calendar day, and distribute daily activity load across the waking window.
24. Model sixteen muscle groups. Present a finer display taxonomy that maps onto them, and never claim regional resolution within a muscle group.
25. Derive coefficients for user-created exercises rather than refusing them, mark those coefficients as derived, and let confidence — never the dose itself — carry the consequence.
26. Record exercises that are not load × repetitions, and exclude them from the resistance dose model until a separate effort model exists for them.
27. Condition the autonomic expectation on recent training load, and use the residual rather than the raw deviation from a rolling baseline.
28. Never present wearable data as a model output. It is evidence entering the system, and the information flows one way.
29. Let persistent unexplained autonomic deviation reduce confidence rather than silently move the recovery multiplier.

---

# 20. References

Bellenger, C. R., Fuller, J. T., Thomson, R. L., Davison, K., Robertson, E. Y., & Buckley, J. D. (2016). **Monitoring Athletic Training Status Through Autonomic Heart Rate Regulation: A Systematic Review and Meta-Analysis.** *Sports Medicine, 46*, 1461–1486. https://doi.org/10.1007/s40279-016-0484-2. PMID: 26888648.

Cao, R., Azimi, I., Sarhaddi, F., Niela-Vilen, H., Axelin, A., Liljeberg, P., & Rahmani, A. M. (2022). **Accuracy Assessment of Oura Ring Nocturnal Heart Rate and Heart Rate Variability in Comparison With Electrocardiography in Time and Frequency Domains: Comprehensive Analysis.** *Journal of Medical Internet Research, 24*(1), e27487. https://doi.org/10.2196/27487. PMID: 35040799.

Craven, J., McCartney, D., Desbrow, B., Sabapathy, S., Bellinger, P., Roberts, L., & Irwin, C. (2022). **Effects of Acute Sleep Loss on Physical Performance: A Systematic and Meta-Analytical Review.** *Sports Medicine, 52*, 2669–2690. https://doi.org/10.1007/s40279-022-01706-y. PMID: 35708888.

Currier, B. S., McLeod, J. C., Banfield, L., et al. (2023). **Resistance training prescription for muscle strength and hypertrophy in healthy adults: a systematic review and Bayesian network meta-analysis.** *British Journal of Sports Medicine, 57*, 1211–1220. https://doi.org/10.1136/bjsports-2023-106807. PMID: 37414459.

Imbach, F., Sutton-Charani, N., Montmain, J., Candau, R., & Perrey, S. (2022). **The Use of Fitness-Fatigue Models for Sport Performance Modelling: Conceptual Issues and Contributions from Machine-Learning.** *Sports Medicine - Open, 8*, 29. https://doi.org/10.1186/s40798-022-00426-x. PMID: 35239054.

Impellizzeri, F. M., Tenan, M. S., Kempton, T., Novak, A., & Coutts, A. J. (2020). **Acute:Chronic Workload Ratio: Conceptual Issues and Fundamental Pitfalls.** *International Journal of Sports Physiology and Performance, 15*, 907–913. https://doi.org/10.1123/ijspp.2019-0864. PMID: 32502973.

Morán-Navarro, R., Pérez, C. E., Mora-Rodríguez, R., de la Cruz-Sánchez, E., González-Badillo, J. J., Sánchez-Medina, L., & Pallarés, J. G. (2017). **Time course of recovery following resistance training leading or not to failure.** *European Journal of Applied Physiology, 117*, 2387–2399. https://doi.org/10.1007/s00421-017-3725-7. PMID: 28965198.

Nuzzo, J. L., Pinto, M. D., Nosaka, K., & Steele, J. (2024). **Maximal Number of Repetitions at Percentages of the One Repetition Maximum: A Meta-Regression and Moderator Analysis of Sex, Age, Training Status, and Exercise.** *Sports Medicine, 54*, 303–321. https://doi.org/10.1007/s40279-023-01937-7. PMID: 37792272.

Pelland, J. C., Remmert, J. F., Robinson, Z. P., Hinson, S. R., & Zourdos, M. C. (2026). **The Resistance Training Dose Response: Meta-Regressions Exploring the Effects of Weekly Volume and Frequency on Muscle Hypertrophy and Strength Gains.** *Sports Medicine, 56*, 481–505. https://doi.org/10.1007/s40279-025-02344-w. PMID: 41343037.

Refalo, M. C., Remmert, J. F., Pelland, J. C., Robinson, Z. P., Zourdos, M. C., Hamilton, D. L., Fyfe, J. J., & Helms, E. R. (2024). **Accuracy of Intraset Repetitions-in-Reserve Predictions During the Bench Press Exercise in Resistance-Trained Male and Female Subjects.** *Journal of Strength and Conditioning Research, 38*, e78–e85. https://doi.org/10.1519/JSC.0000000000004653. PMID: 37967832.

Robinson, Z. P., Pelland, J. C., Remmert, J. F., et al. (2024). **Exploring the Dose-Response Relationship Between Estimated Resistance Training Proximity to Failure, Strength Gain, and Muscle Hypertrophy: A Series of Meta-Regressions.** *Sports Medicine, 54*, 2209–2231. https://doi.org/10.1007/s40279-024-02069-2. PMID: 38970765.

Svensson, T., Madhawa, K., Hoang, N. T., Chung, U.-I., & Kishi Svensson, A. (2024). **Validity and reliability of the Oura Ring Generation 3 with Oura Sleep Staging Algorithm 2.0 when compared to multi-night ambulatory polysomnography.** *Sleep Medicine, 115*, 251–263. https://doi.org/10.1016/j.sleep.2024.01.020. PMID: 38382312.

Thomas, K., Brownstein, C. G., Dent, J., Parker, P., Goodall, S., & Howatson, G. (2018). **Neuromuscular Fatigue and Recovery after Heavy Resistance, Jump, and Sprint Training.** *Medicine & Science in Sports & Exercise, 50*(12), 2526–2535. https://doi.org/10.1249/MSS.0000000000001733. PMID: 30067591.

Zourdos, M. C., Klemp, A., Dolan, C., et al. (2016). **Novel Resistance Training-Specific Rating of Perceived Exertion Scale Measuring Repetitions in Reserve.** *Journal of Strength and Conditioning Research, 30*(1), 267–275. https://doi.org/10.1519/JSC.0000000000001049. PMID: 26049792.
