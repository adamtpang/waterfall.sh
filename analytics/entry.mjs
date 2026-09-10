import posthog from 'posthog-js';
import { startAnalytics } from './analytics.mjs';
startAnalytics(posthog, window.location, POSTHOG_PUBLIC_TOKEN);
