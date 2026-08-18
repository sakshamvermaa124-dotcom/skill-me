
const styleFix = document.createElement("style");
styleFix.innerHTML = `
@media (max-width: 768px) {
  .sprint-milestones-row {
    grid-template-columns: repeat(2, 1fr) !important;
  }
  .milestone-name {
    white-space: normal !important;
    overflow: visible !important;
    font-size: 0.7rem !important;
  }
  .progress-card, .dash-page, .guide-card, .cert-banner, .dash-header {
    max-width: 100vw !important;
    overflow-x: hidden !important;
    box-sizing: border-box !important;
  }
}
`;
document.head.appendChild(styleFix);

