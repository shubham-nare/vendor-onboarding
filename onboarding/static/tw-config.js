// Apple's palette. Templates use slate (greys), indigo (the accent), emerald / amber / rose / violet (status),
// so each scale is mapped to Apple's own colours here and every page follows.
tailwind.config = { theme: { extend: {
  colors: {
    slate:   { 50: '#F5F5F7', 100: '#EDEDF0', 200: '#E3E3E8', 300: '#D2D2D7', 400: '#A1A1A6', 500: '#86868B', 600: '#6E6E73', 700: '#424245', 800: '#333336', 900: '#1D1D1F' },
    indigo:  { 50: '#F0F6FF', 100: '#E0EDFF', 200: '#C2DBFF', 300: '#8EBEFF', 400: '#4C9BFF', 500: '#147CE5', 600: '#0071E3', 700: '#0066CC', 800: '#0053A6', 900: '#003F80' },
    emerald: { 50: '#EAF8EE', 100: '#D2F2DB', 200: '#A6E5B6', 300: '#6FD48B', 400: '#34C759', 500: '#2AB04C', 600: '#248A3D', 700: '#1D7A35', 800: '#17612A', 900: '#0F451D' },
    amber:   { 50: '#FFF5E8', 100: '#FFE9CC', 200: '#FFD399', 300: '#FFB85C', 400: '#FF9F0A', 500: '#FF9500', 600: '#E07800', 700: '#C24E00', 800: '#9E3D00', 900: '#702B00' },
    rose:    { 50: '#FFEFEE', 100: '#FFDDDA', 200: '#FFBAB4', 300: '#FF8A80', 400: '#FF5A4F', 500: '#FF3B30', 600: '#E3241A', 700: '#D70015', 800: '#A80011', 900: '#7A000C' },
    violet:  { 50: '#F8F0FC', 100: '#F0DEF9', 200: '#E0BEF2', 300: '#CB93E8', 400: '#BF5AF2', 500: '#AF52DE', 600: '#8944AB', 700: '#7A3A99', 800: '#5E2D77', 900: '#432055' },
  },
  fontFamily: {
    sans: ['-apple-system', 'BlinkMacSystemFont', '"SF Pro Text"', 'Inter', '"Helvetica Neue"', 'Helvetica', 'Arial', 'sans-serif'],
    display: ['-apple-system', 'BlinkMacSystemFont', '"SF Pro Display"', 'Inter', '"Helvetica Neue"', 'Helvetica', 'Arial', 'sans-serif'],
    mono: ['"SF Mono"', 'ui-monospace', 'Menlo', 'Consolas', 'monospace'],
  },
  boxShadow: { card: 'none', pop: '0 12px 40px rgba(0,0,0,.12)' },
} } };
document.documentElement.classList.add('js');
