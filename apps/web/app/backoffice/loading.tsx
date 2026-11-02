export default function BackofficeLoading() {
  return <div className="metric-skeleton" aria-label="Carregando backoffice">{Array.from({ length: 8 }).map((_, index) => <i key={index} />)}</div>;
}
