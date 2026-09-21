/** The QuantumRoute mark, the same drawing as public/favicon.svg: a quantum orbit with a particle on it, and a route that starts at the
 *  depot in the middle, leaves through the gap (the tail of a Q), bends and ends at a stop. */
export default function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg className="brand-logo" width={size} height={size} viewBox="0 0 64 64" role="img" aria-label="QuantumRoute logo">
      <defs>
        <linearGradient id="qr-bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#dc4a5f" />
          <stop offset="1" stopColor="#8f2233" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="15" fill="url(#qr-bg)" />
      <path d="M33.6 43.2 A16 16 0 1 1 43.2 33.6" fill="none" stroke="#fff" strokeWidth="5" strokeLinecap="round" />
      <path d="M28 28 L40 40 L47 40 L47 51" fill="none" stroke="#ffd166" strokeWidth="4.2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="28" cy="28" r="5.2" fill="#fff" />
      <circle cx="47" cy="52" r="4.8" fill="#fff" stroke="#ffd166" strokeWidth="3" />
      <circle cx="16.7" cy="16.7" r="3.2" fill="#ffd166" stroke="#a52a3c" strokeWidth="1.6" />
    </svg>
  );
}
