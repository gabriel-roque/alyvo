export default function BackofficeLoading() {
  return <main className="backoffice-shell"><aside className="backoffice-sidebar" /><section className="backoffice-main"><div className="metric-skeleton" aria-label="Carregando backoffice">{Array.from({ length: 8 }).map((_, index) => <i key={index} />)}</div></section></main>;
}
