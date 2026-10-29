import Link from "next/link";

export function Brand() {
  return (
    <Link href="/" className="brand" aria-label="Alyvo — página inicial">
      Alyvo<span className="brand-dot" aria-hidden="true" />
    </Link>
  );
}

