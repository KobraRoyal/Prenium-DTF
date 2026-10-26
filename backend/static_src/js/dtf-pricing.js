/** Public estimate only. Integers preserve cent rounding, including fractional laize. */
export function estimateVolume(config, requestedVolume) {
  const volume = Math.min(
    500,
    Math.max(1, Math.round(Number(requestedVolume) || 1)),
  );
  const tier = config.tiers.reduce(
    (best, row) => (Number(row.minimum) <= volume ? row : best),
    null,
  );
  const basisPoints = tier ? Math.round(Number(tier.percent) * 100) : 0;
  const numerator = config.pricePerSqmCents * config.widthCm;
  const cents = (meters, rate) =>
    Math.round((numerator * meters * rate) / 1_000_000);
  const totalCents = cents(volume, 10000 - basisPoints);
  return {
    volume,
    percent: basisPoints / 100,
    minimum: tier ? Number(tier.minimum) : 0,
    unitCents: cents(1, 10000 - basisPoints),
    totalCents,
    savingsCents: cents(volume, 10000) - totalCents,
  };
}
