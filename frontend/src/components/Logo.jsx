export default function Logo({ size = 22, title = 'FinnSpark' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" role="img" aria-label={title}>
      <rect width="64" height="64" rx="8" fill="#174950" />
      <polygon points="35 7 11 36 33 36 30 55 54 26 33 26" fill="#52bc7e" />
      <circle cx="51.5" cy="12" r="3.2" fill="#8cd2a9" />
      <circle cx="56" cy="19.5" r="1.8" fill="#8cd2a9" opacity="0.7" />
    </svg>
  )
}
