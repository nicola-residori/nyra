function formatNyraTimestamp(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);

  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    fractionalSecondDigits: 3,
    hour12: false,
  }).format(date);
}

function localizeNyraTimestamps(root = document) {
  root.querySelectorAll('[data-nyra-timestamp]').forEach((element) => {
    element.textContent = formatNyraTimestamp(element.dataset.nyraTimestamp);
  });
}

document.addEventListener('DOMContentLoaded', () => localizeNyraTimestamps());
