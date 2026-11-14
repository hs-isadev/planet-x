/* Plain-language reading of the Spectrum / Flux-over-time graph.
 *
 * explain(rows, result, mode, context) -> {headline, paragraphs: [string], facts: [[label, value]]}
 *
 * Everything here is computed from the plotted points (the same rows the chart draws), so the
 * words change with the filters. It describes the shape of the data and what that shape usually
 * means; it never claims a detection the dip checks did not make.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SpectrumStory = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Known targets, matched by coordinates (0.5°) or by the session/field name.
  const TARGETS = [
    {key: "barnard", ra: 269.452, dec: 4.693, name: "Barnard's Star",
     kind: "a cool red dwarf (about 3,200 K)",
     expect: "A star this cool is brightest around 1–1.5 µm on this scale, then fades steadily toward longer wavelengths. Watch for a mild dip near 2.7 µm from water in its atmosphere.",
     tip: "Barnard's Star is the fastest-moving star on the sky. Use the motion tools on the images, not this graph, to see it move.",
     timeTip: "Red dwarfs can flare, but in the infrared Barnard's Star should look almost constant. A big change usually means the aperture drifted off the star as it moved."},
    {key: "epsilon", ra: 330.84, dec: -56.79, name: "Epsilon Indi B",
     kind: "a pair of brown dwarfs (about 1,300 K and 900 K)",
     expect: "Brown dwarfs this cold have methane in their atmospheres. Expect a deep hole near 3.3 µm and a peak of light around 4 µm.",
     tip: "The 10′ field also contains the much brighter star Epsilon Indi A. Make sure the aperture is on the brown dwarf, not the star."},
    {key: "wise", ra: 133.795, dec: -7.245, name: "WISE 0855−0714",
     kind: "the coldest known brown dwarf (about 285 K, near room temperature)",
     expect: "Almost all of its light comes out beyond 4 µm. At short wavelengths it should be at or near zero, and it should rise sharply at the red end.",
     tip: "At short wavelengths this object is fainter than the noise. Points near zero there are expected, not a failure.",
     timeTip: "Pick a wavelength window near 4.5 µm. Elsewhere WISE 0855 is too faint for a meaningful light curve."},
    {key: "rw", ra: 76.956, dec: 30.401, name: "RW Aurigae",
     kind: "a young T Tauri star still surrounded by a dusty disk",
     expect: "The star alone would fade toward long wavelengths. The warm dust in its disk adds extra infrared light, so a flat or rising red end is the dust's signature.",
     tip: "RW Aur changes brightness by large amounts. Points from different dates can disagree because the star changed, not because of noise.",
     timeTip: "RW Aur has dimmed by more than a factor of ten in past episodes, when dust from its disk crossed our line of sight. Large swings here are expected."},
    {key: "rdraconis", ra: 248.17, dec: 66.75, name: "R Draconis",
     kind: "a pulsating Mira-type red giant",
     expect: "Cool giants have strong water absorption near 1.4, 1.9 and 2.7 µm, so the spectrum should look lumpy, with dips between brighter windows.",
     tip: "Mira variables brighten and fade over about 8 months, and points here come from several dates. Use Flux over time to see the pulsation.",
     timeTip: "R Draconis pulsates with a period of about 245 days. With a year or more of dates you should see at least one full rise and fall."},
    {key: "vesta", name: "Vesta",
     kind: "an asteroid seen by reflected sunlight",
     expect: "At short wavelengths you see sunlight bounced off the surface, with a pyroxene mineral dip near 0.9–1 µm. Beyond about 3.5 µm Vesta's own warmth starts to add thermal glow.",
     tip: "Vesta moves across the field between dates, so each point is a different place on the sky.",
     timeTip: "Vesta's brightness changes as its distance from the Sun and Earth changes, and as it spins (about every 5.3 hours). Some change is expected."},
  ];

  const finite = v => typeof v === "number" && Number.isFinite(v);
  const fmt = v => {
    const a = Math.abs(v);
    if (!finite(v)) return "—";
    if (a >= 1000) return Math.round(v).toLocaleString("en-US");
    if (a >= 100) return v.toFixed(0);
    if (a >= 10) return v.toFixed(1);
    if (a >= 1) return v.toFixed(2);
    return v.toPrecision(2);
  };
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const dateOf = mjd => new Date((mjd - 40587) * 86400000).toISOString().slice(0, 10);

  function matchTarget(context = {}) {
    const name = String(context.name || "").toLowerCase();
    for (const t of TARGETS) {
      if (name && (name.includes(t.key) || name.includes(t.name.toLowerCase().split(/[ ’']/)[0]))) return t;
    }
    if (finite(context.ra) && finite(context.dec)) {
      for (const t of TARGETS) {
        if (!finite(t.ra)) continue;
        const dRa = (((context.ra - t.ra + 540) % 360) - 180) * Math.cos(t.dec * Math.PI / 180);
        if (Math.hypot(dRa, context.dec - t.dec) < .5) return t;
      }
    }
    return null;
  }

  // Weighted least squares y = a + b x. Returns slope, its error and reduced chi-square.
  function wls(xs, ys, ws) {
    let S = 0, Sx = 0, Sy = 0, Sxx = 0, Sxy = 0;
    for (let i = 0; i < xs.length; i++) { S += ws[i]; Sx += ws[i] * xs[i]; Sy += ws[i] * ys[i]; Sxx += ws[i] * xs[i] ** 2; Sxy += ws[i] * xs[i] * ys[i]; }
    const D = S * Sxx - Sx * Sx;
    if (!(D > 0)) return null;
    const b = (S * Sxy - Sx * Sy) / D, a = (Sy - b * Sx) / S;
    let chi = 0;
    for (let i = 0; i < xs.length; i++) chi += ws[i] * (ys[i] - a - b * xs[i]) ** 2;
    return {a, b, err: Math.sqrt(S / D), chi2: xs.length > 2 ? chi / (xs.length - 2) : NaN};
  }

  function weightedMean(rows) {
    let s = 0, w = 0;
    for (const p of rows) { const wi = 1 / Math.max(p.flux_error, 1e-9) ** 2; s += wi * p.flux; w += wi; }
    const mean = s / w;
    let chi = 0;
    for (const p of rows) chi += (p.flux - mean) ** 2 / Math.max(p.flux_error, 1e-9) ** 2;
    return {mean, err: Math.sqrt(1 / w), chi2: rows.length > 1 ? chi / (rows.length - 1) : NaN};
  }

  // Median brightness in wavelength bins, used to find where the light peaks.
  function binned(rows, edges) {
    const out = [];
    for (let i = 0; i < edges.length - 1; i++) {
      const values = rows.filter(p => p.wavelength >= edges[i] && p.wavelength < edges[i + 1]).map(p => p.flux).sort((a, b) => a - b);
      if (values.length >= 2) out.push({center: (edges[i] + edges[i + 1]) / 2, flux: values[values.length >> 1], n: values.length});
    }
    return out;
  }

  function shapeSentence(alpha, alphaErr) {
    if (!finite(alpha)) return null;
    const sure = Math.abs(alpha) > 2 * (alphaErr || 0);
    if (alpha < -2.6) return ["falls off very steeply toward longer wavelengths",
      "That is steeper than an ordinary star's tail, which usually means a hot star, or that the short-wavelength points are brighter for another reason (a nearby source or a bright date)."];
    if (alpha < -1.4) return ["fades smoothly toward longer wavelengths",
      "This is what a normal star looks like in the infrared: the far side of its thermal glow, which drops roughly like λ⁻² (the Rayleigh–Jeans tail). No obvious extra infrared light is needed to explain it."];
    if (alpha < -.5) return ["fades toward longer wavelengths, but more gently than a bare star",
      "A shallower fall-off often means something is adding infrared light: a cooler companion, warm dust, or a cool atmosphere whose molecules reshape the curve."];
    if (alpha < .5 || !sure) return ["is roughly flat across the range",
      "A flat infrared spectrum usually means a cool object whose light peaks inside this range, or a star plus warm dust that fills in the red end. It can also mean the signal is weak and the points are mostly noise."];
    return ["rises toward longer wavelengths",
      "Brightening toward the red is the sign of something cold or dusty: a brown dwarf, a dust-wrapped young star, an asteroid's own heat, or a dusty galaxy. A normal star never does this on its own."];
  }

  function explainSpectrum(rows, result, target) {
    const paragraphs = [], facts = [];
    const waves = rows.map(p => p.wavelength), lo = Math.min(...waves), hi = Math.max(...waves);
    const detectors = [...new Set(rows.map(p => p.detector))].sort();
    const dates = new Set(rows.map(p => String(p.timestamp || "").slice(0, 10)));
    const snr = rows.map(p => p.flux / Math.max(p.flux_error, 1e-9)).sort((a, b) => a - b);
    const medianSnr = snr[snr.length >> 1];
    const flagged = rows.filter(p => !p.chemical_eligible).length;

    facts.push(["Points", String(rows.length)], ["Wavelengths", `${lo.toFixed(2)}–${hi.toFixed(2)} µm`],
      ["Detectors", detectors.map(d => "D" + d).join(", ")], ["Dates mixed", String(dates.size)],
      ["Typical S/N", fmt(medianSnr)]);

    let headline;
    const strong = snr.filter(v => v > 3).length / snr.length;
    if (strong < .15) {
      headline = "Mostly noise: the source is too faint here to read a shape.";
      paragraphs.push(`The typical point is only ${fmt(medianSnr)}× its own error bar, so most of the scatter is measurement noise. Treat any apparent bumps or dips as unproven. A brighter target, a better-centred aperture, or more dates will help.`);
    } else if (medianSnr < 2) {
      paragraphs.push(`Only ${Math.round(strong * 100)}% of the points stand clearly above the noise, so the shape described below is set by those points. The rest are consistent with little or no light at their wavelengths.`);
    }

    // Spectral slope: log F vs log λ, using only clearly positive points.
    const good = rows.filter(p => p.flux > 2 * p.flux_error && p.flux > 0);
    let alpha = NaN, alphaErr = NaN;
    if (good.length >= 4 && Math.log(Math.max(...good.map(p => p.wavelength)) / Math.min(...good.map(p => p.wavelength))) > .4) {
      const fit = wls(good.map(p => Math.log(p.wavelength)), good.map(p => Math.log(p.flux)),
        good.map(p => (p.flux / p.flux_error) ** 2));
      if (fit) { alpha = fit.b; alphaErr = fit.err * Math.sqrt(Math.max(1, fit.chi2 || 1)); }
    }
    const shape = shapeSentence(alpha, alphaErr);
    if (shape) {
      headline = headline || `The light ${shape[0]}.`;
      paragraphs.push(`Overall the brightness ${shape[0]} (slope ≈ λ^${alpha.toFixed(1)}). ${shape[1]}`);
      facts.push(["Slope", `λ^${alpha.toFixed(2)} ± ${alphaErr < .01 ? "<0.01" : alphaErr.toFixed(2)}`]);
    }

    if (good.length >= 3 && strong < .85) {
      const gLo = Math.min(...good.map(p => p.wavelength)), gHi = Math.max(...good.map(p => p.wavelength));
      if (gLo - lo > 1 && hi - gHi < .5) {
        headline = headline || "Light is only detected at the red, long-wavelength end.";
        paragraphs.push(`Clear signal appears only between ${gLo.toFixed(1)} and ${gHi.toFixed(1)} µm. Shortward of that the object is fainter than the noise. Only very cold objects (cool brown dwarfs, dust, distant red galaxies) look like this.`);
      } else if (hi - gHi > 1 && gLo - lo < .5) {
        headline = headline || "Light is only detected at the blue, short-wavelength end.";
        paragraphs.push(`Clear signal appears only between ${gLo.toFixed(1)} and ${gHi.toFixed(1)} µm. Beyond that it fades into the noise, as expected for a faint star whose light drops toward the infrared.`);
      }
    }

    // Peak location -> rough temperature, only when the peak sits inside the range.
    const edges = [];
    for (let w = .75; w <= 5.01; w += .25) edges.push(w);
    const bins = binned(good.length >= 6 ? good : rows, edges);
    if (bins.length >= 5) {
      let peak = bins[0];
      for (const b of bins) if (b.flux > peak.flux) peak = b;
      const inside = peak !== bins[0] && peak !== bins[bins.length - 1];
      if (inside && strong >= .3) {
        const temperature = 5100 / peak.center; // peak of F_nu for a blackbody, in K
        paragraphs.push(`The light peaks near ${peak.center.toFixed(2)} µm. If this were a simple glowing body, that peak would mean a temperature of roughly ${Math.round(temperature / 50) * 50} K. Real atmospheres have molecular bands, so take this as a ballpark, not a measurement.`);
        facts.push(["Peak", `~${peak.center.toFixed(2)} µm`]);
      } else if (peak === bins[0] && strong >= .3) {
        paragraphs.push("The brightest part is at the blue (left) edge, so the peak of the light lies below about 0.9 µm. For a simple glowing body that means hotter than roughly 5,500 K. For a cool star it can instead mean the short-wavelength points include light from a neighbour.");
      } else if (peak === bins[bins.length - 1] && strong >= .3) {
        paragraphs.push("The brightest part is at the red (right) edge, so the light peaks beyond 5 µm. That means a temperature below about 1,000 K, or dust radiating more than the object itself.");
      }
    }

    // Dip / peak checks from the backend (never invented here).
    const checked = (result.candidates || []).filter(c => c.evidence);
    const found = checked.filter(c => c.candidate);
    if (found.length) {
      const list = found.map(c => `${c.name.toLowerCase()} near ${c.center.toFixed(2)} µm (${c.evidence.significance.toFixed(1)}σ)`);
      paragraphs.push(`The dip checks flag ${list.join("; ")}. A flag means the points inside that band sit lower (or higher, for emission) than the neighbouring continuum by more than the noise. That is consistent with the feature. It does not prove the molecule is there, because other materials and the star's own atmosphere can absorb at the same wavelengths.`);
    } else if (checked.length) {
      paragraphs.push(`The ${plural(checked.length, "reference band")} that had enough nearby points (${checked.map(c => c.formula).join(", ")}) show no significant dip or peak. "No dip" means none is visible at this noise level, not that the substance is absent.`);
    }

    // Scatter between neighbouring points.
    if (rows.length >= 8) {
      const sorted = [...rows].sort((a, b) => a.wavelength - b.wavelength);
      let jumps = 0, count = 0;
      for (let i = 1; i < sorted.length; i++) {
        const a = sorted[i - 1], b = sorted[i];
        if (b.wavelength - a.wavelength > .08) continue;
        jumps += (b.flux - a.flux) ** 2 / (a.flux_error ** 2 + b.flux_error ** 2); count++;
      }
      const ratio = count ? jumps / count : NaN;
      if (ratio > 4 && dates.size > 1) {
        paragraphs.push(`Points at almost the same wavelength disagree by about ${fmt(Math.sqrt(ratio))}× more than their error bars allow. These points come from ${dates.size} different dates, so a star that changes brightness will look jagged here. Switch to Flux over time to check for variability.`);
      } else if (ratio > 4) {
        paragraphs.push("Neighbouring points disagree by more than their error bars allow. A nearby source leaking into the aperture or an imperfect background can cause this.");
      }
    }
    if (flagged) paragraphs.push(`${plural(flagged, "point")} ${flagged === 1 ? "is" : "are"} drawn as ×. ${flagged === 1 ? "It" : "They"} failed a quality check (detector flags, poor fit, or edge of frame) and ${flagged === 1 ? "is" : "are"} left out of the dip checks.`);

    if (target) {
      paragraphs.unshift(`This field is ${target.name}, ${target.kind}. ${target.expect}`);
      if (target.tip) paragraphs.push(target.tip);
    }
    return {headline: headline || "Not enough clean points to describe the shape yet.", paragraphs, facts};
  }

  // Weighted sinusoid scan (a small Lomb–Scargle). Returns the best period if it explains most of the variance.
  function bestPeriod(rows, span) {
    const t = rows.map(p => p.mjd), y = rows.map(p => p.flux), w = rows.map(p => 1 / Math.max(p.flux_error, 1e-9) ** 2);
    const W = w.reduce((a, b) => a + b, 0), mean = y.reduce((s, v, i) => s + w[i] * v, 0) / W;
    const total = y.reduce((s, v, i) => s + w[i] * (v - mean) ** 2, 0);
    if (!(total > 0)) return null;
    let best = null;
    const fMin = 1.5 / Math.max(span, 1), fMax = .5, steps = 1800;
    for (let k = 0; k <= steps; k++) {
      const f = fMin * Math.pow(fMax / fMin, k / steps), omega = 2 * Math.PI * f;
      let cc = 0, ss = 0, cs = 0, yc = 0, ys = 0;
      for (let i = 0; i < t.length; i++) {
        const c = Math.cos(omega * t[i]), sn = Math.sin(omega * t[i]), d = y[i] - mean;
        cc += w[i] * c * c; ss += w[i] * sn * sn; cs += w[i] * c * sn; yc += w[i] * d * c; ys += w[i] * d * sn;
      }
      const det = cc * ss - cs * cs;
      if (!(det > 0)) continue;
      const A = (yc * ss - ys * cs) / det, B = (ys * cc - yc * cs) / det;
      const power = (A * yc + B * ys) / total;
      if (!best || power > best.power) best = {days: 1 / f, power};
    }
    return best && best.power > .6 && rows.length >= 10 ? best : null;
  }

  function explainTime(rows, result, target) {
    const paragraphs = [], facts = [];
    const mjds = rows.map(p => p.mjd), first = Math.min(...mjds), last = Math.max(...mjds);
    const days = last - first;
    const dates = new Set(rows.map(p => Math.floor(p.mjd)));
    const center = rows.reduce((s, p) => s + p.wavelength, 0) / rows.length;
    const m = weightedMean(rows);
    facts.push(["Points", String(rows.length)], ["Distinct days", String(dates.size)],
      ["Span", `${dateOf(first)} → ${dateOf(last)} (${Math.round(days)} d)`], ["Band", `~${center.toFixed(2)} µm`],
      ["Mean flux", `${fmt(m.mean)} ± ${fmt(m.err)} µJy`]);

    let headline;
    if (dates.size < 2) {
      return {headline: "Only one day of data: nothing to compare over time yet.",
        paragraphs: ["All points fall on the same day. To see whether the object changes, load more dates (switch Window to All dates, or download more epochs) and measure again."].concat(target ? [`This field is ${target.name}, ${target.kind}.`] : []),
        facts};
    }
    const fit = wls(rows.map(p => (p.mjd - first) / 365.25), rows.map(p => p.flux), rows.map(p => 1 / Math.max(p.flux_error, 1e-9) ** 2));
    const amplitude = Math.max(...rows.map(p => p.flux)) - Math.min(...rows.map(p => p.flux));
    const percent = m.mean > 0 ? 100 * amplitude / m.mean : NaN;
    if (finite(m.chi2) && m.chi2 > 4) {
      headline = "The brightness changes more than the error bars can explain.";
      paragraphs.push(`Compared with a constant brightness, the points scatter about ${fmt(Math.sqrt(m.chi2))}× more than their error bars. The full range is about ${fmt(amplitude)} µJy${finite(percent) ? ` (${Math.round(percent)}% of the average)` : ""}. That is a real change, from the object itself or from something else in the aperture.`);
    } else {
      headline = "The brightness is steady within the uncertainties.";
      paragraphs.push(`The points agree with a constant brightness of about ${fmt(m.mean)} µJy. Any wiggles are within the error bars, so this data shows no variability at about ${center.toFixed(1)} µm.`);
    }
    if (fit && days > 30) {
      const sig = Math.abs(fit.b) / (fit.err * Math.sqrt(Math.max(1, fit.chi2 || 1)));
      if (sig > 3 && m.mean > 0) {
        const perYear = 100 * fit.b / m.mean;
        paragraphs.push(`There is a steady trend: ${perYear > 0 ? "brightening" : "fading"} by about ${Math.abs(perYear).toFixed(0)}% per year (${sig.toFixed(1)}σ). Over a short baseline, a slow trend can also be part of a longer cycle.`);
        facts.push(["Trend", `${perYear > 0 ? "+" : ""}${perYear.toFixed(1)}%/yr`]);
      }
    }
    const period = finite(m.chi2) && m.chi2 > 4 && dates.size >= 10 ? bestPeriod(rows, days) : null;
    if (period) {
      paragraphs.push(`A repeating pattern fits best with a period of about ${period.days >= 2 ? Math.round(period.days) + " days" : (period.days * 24).toFixed(1) + " hours"} (it explains ${Math.round(period.power * 100)}% of the variation). With gaps between dates, half or double that period can fit almost as well, so check it against the target's known behaviour.`);
      facts.push(["Best period", period.days >= 2 ? `~${Math.round(period.days)} d` : `~${(period.days * 24).toFixed(1)} h`]);
    }
    if (days < 60) paragraphs.push(`The data covers only ${Math.round(days)} days. Slow variables (Mira stars cycle over hundreds of days) need a longer span.`);
    paragraphs.push("Points are restricted to a narrow wavelength window, so the changes here are not caused by mixing different colours of light.");
    if (target) {
      paragraphs.unshift(`This field is ${target.name}, ${target.kind}.`);
      if (target.timeTip) paragraphs.push(target.timeTip);
    }
    return {headline, paragraphs, facts};
  }

  function explain(rows, result, mode, context = {}) {
    rows = (rows || []).filter(p => finite(p.flux) && finite(p.flux_error) && (mode === "time" ? finite(p.mjd) : finite(p.wavelength)));
    const target = matchTarget(context);
    if (!rows.length) return {headline: "No points match the current filters.", paragraphs: ["Loosen the filters (all releases, show flagged points, or a wider window) to see measurements."], facts: []};
    return mode === "time" ? explainTime(rows, result || {}, target) : explainSpectrum(rows, result || {}, target);
  }

  return {explain, matchTarget, TARGETS};
});
