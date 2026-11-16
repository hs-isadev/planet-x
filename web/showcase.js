const assets = "/assets/showcase/";
const chapters = [
  {
    id: "exposures", label: "Observations", title: "Meet Barnard’s Star",
    text: "Start with real SPHEREx infrared images of the same patch of sky. Use the timeline to move through observing dates and watch how the field changes.",
    instructions: [
      ["Play or scrub", "Use the timeline to watch the sequence or stop on a specific date."],
      ["Inspect an exposure", "Check its detector, date and quality flags. Download the original FITS for the pixel values and metadata."],
      ["Search another field", "Enter coordinates or pick a saved star. Search archive looks for more observations and can load them in batches."]
    ],
    action: "Open Barnard’s Star"
  },
  {
    id: "motion", label: "Track point", title: "Measure a shift in position",
    text: "Motion pair opens two comparable Barnard’s Star observations side by side. The rings mark centroids measured from the FITS pixels.",
    instructions: [
      ["Open Motion pair", "Zoom in and look at the marked source on both dates."],
      ["Click the source, then Track point", "Parallax fits the source position in compatible exposures and plots offsets across the dates it can measure."],
      ["Check the fit", "Compare measurements from the same detector at similar wavelengths. Read the uncertainty and any rejected frames before interpreting a shift."]
    ],
    action: "Open the measured pair"
  },
  {
    id: "spectrum", label: "Spectrum", title: "Read the infrared spectrum",
    text: "The spectrum samples how much infrared light the selected source contributes at different wavelengths. Select a dot to inspect a real Barnard’s Star measurement.",
    instructions: [
      ["Across · wavelength (µm)", "Move right for longer-wavelength infrared light."],
      ["Up · flux density (µJy)", "A higher dot means more measured light at that wavelength. Vertical bars show the estimated measurement uncertainty."],
      ["Read dips in context", "Compare nearby wavelengths and check dates, flags and uncertainty. A dip is only a candidate absorption feature until it is confirmed."]
    ],
    action: "Open spectrum controls"
  },
  {
    id: "earth", label: "3D Context", title: "Trace your way back to Earth",
    text: "Open Barnard’s Star in 3D Context. Its position comes from catalog direction and distance. The flight and planet globes are rendered scene geometry.",
    instructions: [
      ["Focus on the star", "Orbit or zoom to see it in its stellar neighborhood."],
      ["Trace back to Earth", "Press the control in the object inspector once it becomes available. The camera flies into the Solar System toward Earth."],
      ["Look back at the sky", "At Earth, read the target’s constellation and light travel time. Choose Return to object to fly back."],
      ["Find the belts", "In Solar System view, use Overview to see the illustrative asteroid populations and the icy Kuiper Belt. Toggle them in Scale / orbit."]
    ],
    action: "Open Barnard’s 3D context"
  },
  {
    id: "satellite", label: "Satellite View", title: "Pick a patch of sky",
    text: "Satellite View connects a direction on the sky to the infrared exposures and the catalog-based 3D view.",
    instructions: [
      ["Look around", "Drag the view and use the reticle to see the direction you are pointing toward."],
      ["Pin a target", "Right-click a sky position to open its SPHEREx cutouts and pin the direction."],
      ["Switch perspectives", "Use the pinned target to move between the sky, the observations and the 3D context."]
    ],
    action: "Open Satellite View"
  }
];

function observedField() {
  return `<figure class="pg-observed">
    <img src="${assets}late-field.webp" alt="An archived SPHEREx infrared cutout centered on the field of Barnard’s Star">
    <span class="pg-reticle" aria-hidden="true"></span>
    <figcaption><strong>Barnard’s Star field</strong><span>05 May 2026 · Detector 6 · 10′ field</span></figcaption>
  </figure>`;
}

function measuredPair(data) {
  const marked = (point, index) => `<figure class="pg-epoch">
    <div><img src="${assets}${index ? "late" : "early"}-detail.webp" alt="Enlarged detector image from ${point.date}">
    <span class="pg-centroid" style="--point-x:${point.xy[0]}%;--point-y:${point.xy[1]}%" aria-hidden="true"></span></div>
    <figcaption><strong>${point.date}</strong><span>D${point.detector} · ${point.wavelength.toFixed(3)} µm</span></figcaption>
  </figure>`;
  return `<div class="pg-pair">${data.motion.map(marked).join("")}</div>
    <div class="pg-measurement"><strong>${data.separation_arcsec.toFixed(2)}″</strong><span>Measured centroid shift over ${data.baseline_days.toFixed(1)} days</span></div>`;
}

function spectrumPlot(points) {
  const horizontal = wave => (wave - 1.25) / (5 - 1.25) * 100;
  const vertical = flux => (11.5 - flux / 1e6) / (11.5 - 5) * 100;
  return `<figure class="pg-spectrum">
    <figcaption><strong>Barnard’s Star · sample spectrum</strong><span>Four archived QR2 measurements</span></figcaption>
    <div class="pg-chart-y">Flux density (million µJy)</div>
    <div class="pg-chart" role="group" aria-label="Measured flux density by infrared wavelength">
      ${[6, 8, 10].map(v => `<span class="pg-gridline" style="--line-y:${vertical(v * 1e6)}%"><span>${v}</span></span>`).join("")}
      ${[2, 3, 4, 5].map(v => `<span class="pg-chart-tick" style="--tick-x:${horizontal(v)}%">${v}</span>`).join("")}
      ${points.map((point, i) => `<div class="pg-datum pg-datum-${point.detector}" style="--point-x:${horizontal(point.wavelength)}%;--point-y:${vertical(point.flux_ujy)}%;--error:${point.sigma_ujy * 2 / 6.5e6 * 100}%">
        <span class="pg-error" aria-hidden="true"></span>
        <button type="button" data-spectrum-point="${i}" aria-pressed="false" aria-label="Detector ${point.detector}, ${point.wavelength.toFixed(3)} micrometers"></button>
      </div>`).join("")}
    </div>
    <div class="pg-chart-x">Wavelength (µm)</div>
    <p class="pg-chart-reading" aria-live="polite"></p>
  </figure>`;
}

function earthFlight() {
  return `<figure class="pg-earth">
    <div class="pg-flight-origin"><span aria-hidden="true"></span>Barnard’s Star</div>
    <div class="pg-flight-path" aria-hidden="true"></div>
    <img src="${assets}earth.webp" alt="Illustrative sunlit globe rendered using the project’s Earth surface map">
    <figcaption><strong>Earth</strong><span>Illustrated flight · NASA Blue Marble surface</span></figcaption>
  </figure>`;
}

function satelliteView() {
  return `<figure class="pg-satellite">
    <img src="${assets}satellite.webp" alt="The app’s Satellite View showing a dense star field">
    <span class="pg-reticle" aria-hidden="true"></span>
    <figcaption><strong>Satellite View</strong><span>Star-map backdrop used in the app</span></figcaption>
  </figure>`;
}

const loadEvidence = () => fetch(assets + "barnard.json").then(response => {
  if (!response.ok) throw new Error("Guide measurements could not load.");
  return response.json();
});

export function installShowcase({openLab, openContext, openSatellite}) {
  const dialog = document.createElement("dialog");
  dialog.className = "pg-guide";
  dialog.setAttribute("aria-labelledby", "pg-heading");
  dialog.innerHTML = `<div class="pg-shell">
    <header class="pg-header"><h2 id="pg-heading">Parallax field guide</h2>
      <button type="button" data-close aria-label="Close field guide" autofocus>×</button></header>
    <nav class="pg-chapters" aria-label="Guide chapters">
      ${chapters.map((chapter, index) => `<button type="button" data-chapter="${index}">${chapter.label}</button>`).join("")}
    </nav>
    <section class="pg-main" aria-labelledby="pg-chapter-title">
      <div class="pg-visual"></div>
      <div class="pg-copy"></div>
    </section>
    <footer class="pg-footer">
      <button type="button" data-previous>← Previous</button>
      <span data-progress aria-live="polite"></span>
      <button type="button" data-next>Next →</button>
    </footer>
  </div>`;
  document.body.append(dialog);
  const find = selector => dialog.querySelector(selector);
  const visual = find(".pg-visual");
  const previous = find("[data-previous]");
  const next = find("[data-next]");
  let active = 0, evidence;

  async function show(index) {
    active = index;
    const chapter = chapters[active];
    dialog.querySelectorAll("[data-chapter]").forEach((button, i) => {
      if (i === active) button.setAttribute("aria-current", "step");
      else button.removeAttribute("aria-current");
    });
    find(".pg-copy").innerHTML = `<h3 id="pg-chapter-title">${chapter.title}</h3><p>${chapter.text}</p>
      <ol>${chapter.instructions.map(([label, text]) => `<li><strong>${label}</strong><span>${text}</span></li>`).join("")}</ol>
      <button type="button" class="pg-action">${chapter.action} <span aria-hidden="true">↗</span></button>`;
    find(".pg-action").onclick = () => {
      dialog.close();
      if (chapter.id === "earth") openContext();
      else if (chapter.id === "satellite") openSatellite();
      else openLab(chapter.id);
    };
    find("[data-progress]").textContent = `${active + 1} of ${chapters.length}`;
    previous.disabled = active === 0;
    next.textContent = active === chapters.length - 1 ? "Done" : "Next →";
    if (chapter.id === "exposures") visual.innerHTML = observedField();
    if (chapter.id === "earth") visual.innerHTML = earthFlight();
    if (chapter.id === "satellite") visual.innerHTML = satelliteView();
    if (chapter.id !== "motion" && chapter.id !== "spectrum") return;
    visual.textContent = "Loading archived measurements…";
    try {
      const data = await (evidence ??= loadEvidence());
      if (active !== index) return;
      visual.innerHTML = chapter.id === "motion" ? measuredPair(data) : spectrumPlot(data.spectrum);
      if (chapter.id === "spectrum") {
        const buttons = [...dialog.querySelectorAll("[data-spectrum-point]")];
        const inspect = i => {
          const point = data.spectrum[i];
          const formatFlux = n => Math.round(n).toLocaleString("en-US");
          buttons.forEach((button, position) => button.setAttribute("aria-pressed", String(position === i)));
          find(".pg-chart-reading").textContent =
            `${point.wavelength.toFixed(3)} µm · ${formatFlux(point.flux_ujy)} ± ${formatFlux(point.sigma_ujy)} µJy · D${point.detector} · ${point.date}`;
        };
        buttons.forEach((button, i) => button.onclick = () => inspect(i));
        inspect(0);
      }
    } catch {
      evidence = undefined;
      if (active === index) visual.textContent = "The archived measurements are unavailable. You can still open the tool below.";
    }
  }

  dialog.querySelectorAll("[data-chapter]").forEach((button, i) => button.onclick = () => show(i));
  find("[data-close]").onclick = () => dialog.close();
  previous.onclick = () => show(active - 1);
  next.onclick = () => active === chapters.length - 1 ? dialog.close() : show(active + 1);
  dialog.addEventListener("click", event => { if (event.target === dialog) dialog.close(); });

  function open(chapter) {
    const index = chapters.findIndex(item => item.id === chapter);
    show(index < 0 ? 0 : index);
    if (!dialog.open) dialog.showModal();
  }
  return open;
}
