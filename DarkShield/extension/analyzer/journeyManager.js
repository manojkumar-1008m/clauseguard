/**
 * DarkShield Phase B5.4 Journey Boundary Manager
 * 
 * Responsibilities:
 * - Opaque immutable journey ID generation (jrn_<uuid4 hex>)
 * - Tab-scoped journey lifecycle management
 * - Registrable domain (eTLD+1) site boundary enforcement
 * - Multi-page stage progression & transition validation
 * - In-place SPA stage transitions (2 of 3 compound observable signals)
 * - Auxiliary context sidecar isolation (privacy, terms, faq, help)
 * - External payment gateway suspension without third-party DOM scraping
 * - Inactivity tracking (5-15 min soft idle, >=15 min hard expiration)
 * - Bounded state management (max 5 journeys/tab, max 20 events/journey)
 * - Absolute privacy preservation (zero PII, credentials, or card details)
 */

(function (root, factory) {
	if (typeof define === 'function' && define.amd) {
		define([], factory);
	} else if (typeof module === 'object' && module.exports) {
		module.exports = factory();
	} else {
		root.JourneyManager = factory();
	}
}(typeof self !== 'undefined' ? self : this, function () {
	'use strict';

	// Configurable Inactivity & Storage Constants (Part 9 & 23)
	const JOURNEY_INACTIVITY_TIMEOUT_MS = 15 * 60 * 1000; // 15 minutes
	const JOURNEY_SOFT_IDLE_TIMEOUT_MS = 5 * 60 * 1000;  // 5 minutes
	const MAX_ACTIVE_JOURNEYS_PER_TAB = 5;
	const MAX_EVENTS_PER_JOURNEY = 20;

	// Canonical Journey Stages (Part 5)
	const STAGES = Object.freeze({
		DISCOVERY: 'DISCOVERY',
		PRODUCT: 'PRODUCT',
		CART: 'CART',
		CHECKOUT: 'CHECKOUT',
		PAYMENT: 'PAYMENT',
		CONFIRMATION: 'CONFIRMATION',
		SUBSCRIPTION: 'SUBSCRIPTION',
		CANCELLATION: 'CANCELLATION',
		RETENTION_STEP: 'RETENTION_STEP',
		TERMINATION: 'TERMINATION',
		UNKNOWN: 'UNKNOWN'
	});

	// Canonical Journey Statuses (Part 4 & 22)
	const STATUSES = Object.freeze({
		ACTIVE: 'ACTIVE',
		IDLE: 'IDLE',
		SUSPENDED: 'SUSPENDED',
		SUSPENDED_EXTERNAL_GATEWAY: 'SUSPENDED_EXTERNAL_GATEWAY',
		COMPLETED: 'COMPLETED',
		ABANDONED: 'ABANDONED',
		EXPIRED_INACTIVE: 'EXPIRED_INACTIVE',
		TERMINATED: 'TERMINATED'
	});

	// Terminal statuses that cannot be silently resumed (Part 22)
	const TERMINAL_STATUSES = new Set([
		STATUSES.COMPLETED,
		STATUSES.ABANDONED,
		STATUSES.EXPIRED_INACTIVE,
		STATUSES.TERMINATED
	]);

	// Known 2-level TLD suffixes for eTLD+1 extraction (Part 8)
	const TWO_LEVEL_TLDS = new Set([
		'co.uk', 'org.uk', 'me.uk', 'ltd.uk', 'plc.uk',
		'co.in', 'net.in', 'org.in', 'gen.in', 'firm.in',
		'com.au', 'net.au', 'org.au', 'edu.au',
		'co.nz', 'net.nz', 'org.nz',
		'com.br', 'net.br', 'org.br',
		'co.jp', 'ne.jp', 'or.jp',
		'co.za', 'org.za',
		'com.sg', 'edu.sg',
		'com.my', 'org.my'
	]);

	// Known payment gateway provider host patterns (Part 13)
	const PAYMENT_GATEWAY_PATTERNS = [
		/paypal\.com$/i,
		/stripe\.com$/i,
		/razorpay\.com$/i,
		/klarna\.com$/i,
		/squareup\.com$/i,
		/adyen\.com$/i,
		/checkout\.com$/i,
		/paytm\.com$/i
	];

	// Informational auxiliary route keywords (Part 12)
	const AUXILIARY_ROUTE_PATTERNS = [
		/\/privacy(\/|-|$|\?)/i,
		/\/terms(\/|-|$|\?)/i,
		/\/tos(\/|-|$|\?)/i,
		/\/faq(\/|-|$|\?)/i,
		/\/help(\/|-|$|\?)/i,
		/\/support(\/|-|$|\?)/i,
		/\/legal(\/|-|$|\?)/i
	];

	/**
	 * Generate an opaque, immutable journey identifier (Part 2).
	 * Format: jrn_<uuid4 hex>
	 */
	function makeJourneyId() {
		// Use crypto.randomUUID if available, else standard fallback
		if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
			return 'jrn_' + crypto.randomUUID().replace(/-/g, '');
		}
		const s4 = () => Math.floor((1 + Math.random()) * 0x10000).toString(16).substring(1);
		return 'jrn_' + s4() + s4() + s4() + s4() + s4() + s4() + s4() + s4();
	}

	/**
	 * Generate an auxiliary context identifier (Part 12).
	 */
	function makeAuxiliaryId() {
		return 'aux_' + Math.random().toString(36).substring(2, 12);
	}

	/**
	 * Extract registrable domain / eTLD+1 from hostname or URL (Part 8).
	 */
	function extractSiteIdentity(urlOrHost) {
		if (!urlOrHost || typeof urlOrHost !== 'string') return 'unknown_site';
		let host = urlOrHost.trim().toLowerCase();
		if (host.includes('://')) {
			try {
				const u = new URL(host);
				host = u.hostname;
			} catch (e) {
				host = host.split('://')[1].split('/')[0];
			}
		} else {
			host = host.split('/')[0].split('?')[0].split('#')[0];
		}
		host = host.split(':')[0]; // Strip port

		if (!host || host === 'localhost' || host === '127.0.0.1' || host === '::1') {
			return host || 'localhost';
		}

		const parts = host.split('.');
		if (parts.length <= 2) return host;

		const lastTwo = parts.slice(-2).join('.');
		if (TWO_LEVEL_TLDS.has(lastTwo) && parts.length >= 3) {
			return parts.slice(-3).join('.');
		}
		return parts.slice(-2).join('.');
	}

	/**
	 * Check if host belongs to a known external payment gateway (Part 13).
	 */
	function isExternalPaymentGateway(host) {
		if (!host) return false;
		return PAYMENT_GATEWAY_PATTERNS.some(pattern => pattern.test(host));
	}

	/**
	 * Check if route represents an auxiliary informational context (Part 12).
	 */
	function isAuxiliaryRoute(routeOrUrl) {
		if (!routeOrUrl || typeof routeOrUrl !== 'string') return false;
		return AUXILIARY_ROUTE_PATTERNS.some(pattern => pattern.test(routeOrUrl));
	}

	/**
	 * Extract non-sensitive product anchor (SKU, item token, title slug) (Part 10).
	 * Strictly ignores any PII, credentials, or form input values (Part 24).
	 */
	function extractProductAnchor(url, route, domContext) {
		const target = (route || url || '').toLowerCase();

		// URL patterns: /product/12345, /item/sku-abc, /p/B00123
		const match = target.match(/\/(?:product|item|dp|p|goods|gp\/product)\/([a-z0-9_-]{3,50})/i);
		if (match && match[1]) {
			return match[1];
		}

		// DOM context product ID or title slug if safely present
		if (domContext && domContext.product_id) {
			return String(domContext.product_id).slice(0, 50);
		}
		if (domContext && domContext.product_slug) {
			return String(domContext.product_slug).slice(0, 50);
		}

		return null;
	}

	/**
	 * Infer canonical journey stage from route and event signals (Part 5).
	 */
	function inferStageFromRouteAndEvent(route, action, text, domContext) {
		const r = (route || '').toLowerCase();
		const t = (text || '').toLowerCase();

		// Cancellation flow
		if (r.includes('cancel') || r.includes('unsubscribe') || r.includes('end-membership')) {
			if (r.includes('offer') || r.includes('retain') || r.includes('save') || r.includes('discount')
				|| (domContext && domContext.has_retention_offer)) {
				return STAGES.RETENTION_STEP;
			}
			if (r.includes('confirm') || r.includes('success') || r.includes('goodbye') || r.includes('terminated')) {
				return STAGES.TERMINATION;
			}
			return STAGES.CANCELLATION;
		}

		if (r.includes('subscription') || r.includes('plan') || r.includes('membership') || r.includes('billing')) {
			return STAGES.SUBSCRIPTION;
		}

		// Purchase flow
		if (r.includes('thank') || r.includes('success') || r.includes('receipt') || r.includes('order-confirm') || r.includes('completed')) {
			return STAGES.CONFIRMATION;
		}
		if (r.includes('pay') || r.includes('payment') || r.includes('billing-step')) {
			return STAGES.PAYMENT;
		}
		if (r.includes('checkout') || r.includes('order') || r.includes('shipping')) {
			return STAGES.CHECKOUT;
		}
		if (r.includes('cart') || r.includes('basket') || r.includes('bag')) {
			return STAGES.CART;
		}
		if (r.includes('product') || r.includes('/item/') || r.includes('/p/') || r.includes('/dp/')) {
			return STAGES.PRODUCT;
		}
		if (r.includes('search') || r.includes('category') || r.includes('catalog') || r.includes('shop')) {
			return STAGES.DISCOVERY;
		}

		return STAGES.UNKNOWN;
	}

	/**
	 * Evaluate in-place SPA stage transitions using 2-of-3 compound signals (Part 14).
	 */
	function evaluateSpaStageTransition(currentStage, event, diffSignals) {
		const dom = event.dom_context || {};
		const text = (event.text || '').toLowerCase();
		const action = String(event.action || '').toUpperCase();

		let signalCount = 0;
		let candidateStage = STAGES.UNKNOWN;

		// Signal 1: DOM landmark transition (Heading / title change)
		const headingText = (dom.heading_text || dom.title || '').toLowerCase();
		if (headingText) {
			if (headingText.includes('payment') || headingText.includes('pay now')) {
				candidateStage = STAGES.PAYMENT;
				signalCount++;
			} else if (headingText.includes('checkout') || headingText.includes('shipping')) {
				candidateStage = STAGES.CHECKOUT;
				signalCount++;
			} else if (headingText.includes('confirmation') || headingText.includes('thank you') || headingText.includes('order placed')) {
				candidateStage = STAGES.CONFIRMATION;
				signalCount++;
			} else if (headingText.includes('cancellation') || headingText.includes('cancel membership')) {
				candidateStage = STAGES.CANCELLATION;
				signalCount++;
			}
		}

		// Signal 2: Intentional forward user action (Proceed, Pay, Place Order, Confirm)
		const isForwardAction = action === 'CLICK' && (
			text.includes('proceed') || text.includes('continue') || text.includes('pay')
			|| text.includes('place order') || text.includes('confirm') || text.includes('next')
		);
		if (isForwardAction) {
			signalCount++;
		}

		// Signal 3: Form signature transition (Presence of diff signals or newly rendered step forms)
		const hasFormSignature = Boolean(
			(diffSignals && diffSignals.length > 0)
			|| dom.has_payment_inputs
			|| dom.is_step_container
			|| (event.snapshot_after && event.snapshot_before)
		);
		if (hasFormSignature) {
			signalCount++;
		}

		// Require at least 2 of 3 compound signals
		if (signalCount >= 2 && candidateStage !== STAGES.UNKNOWN && candidateStage !== currentStage) {
			return candidateStage;
		}

		return null;
	}

	class JourneyManager {
		constructor() {
			this.inactivityTimeoutMs = JOURNEY_INACTIVITY_TIMEOUT_MS;
			this.softIdleTimeoutMs = JOURNEY_SOFT_IDLE_TIMEOUT_MS;
			this.tabStorage = {};
			this.eventHistory = {};
		}

		/**
		 * Create a new Journey State object (Part 4).
		 */
		createJourney(tabId, sessionId, siteIdentity, intentType, initialStage, productAnchor) {
			const now = Date.now();
			return {
				journey_id: makeJourneyId(),
				tab_id: tabId ?? null,
				session_id: sessionId ?? null,
				site_identity: siteIdentity || 'unknown_site',
				intent_type: intentType || 'PURCHASE',
				journey_stage: initialStage || STAGES.UNKNOWN,
				stage_history: initialStage && initialStage !== STAGES.UNKNOWN ? [initialStage] : [],
				status: STATUSES.ACTIVE,
				product_anchor: productAnchor || null,
				anchor_tier: productAnchor ? 'MODERATE' : 'UNKNOWN',
				has_commitment: false,
				ledger: [],
				last_event_timestamp: now,
				created_timestamp: now,
				events_count: 0
			};
		}

		/**
		 * Create an auxiliary context record (Part 12).
		 */
		createAuxiliaryContext(parentJourneyId, route) {
			return {
				auxiliary_id: makeAuxiliaryId(),
				parent_journey_id: parentJourneyId || null,
				is_auxiliary: true,
				route: route || null,
				created_timestamp: Date.now()
			};
		}

		/**
		 * Evaluate inactivity status of a journey (Part 9).
		 */
		evaluateInactivity(journey, now) {
			if (!journey || !journey.last_event_timestamp) return STATUSES.ACTIVE;
			const elapsed = now - journey.last_event_timestamp;
			if (elapsed >= this.inactivityTimeoutMs) {
				return STATUSES.EXPIRED_INACTIVE;
			}
			if (elapsed >= this.softIdleTimeoutMs && journey.status === STATUSES.ACTIVE) {
				return STATUSES.IDLE;
			}
			return journey.status;
		}

		/**
		 * Prune tab journeys bounded to MAX_ACTIVE_JOURNEYS_PER_TAB (Part 23).
		 */
		pruneJourneys(tabJourneys) {
			if (!tabJourneys || typeof tabJourneys !== 'object') return {};
			const keys = Object.keys(tabJourneys);
			if (keys.length <= MAX_ACTIVE_JOURNEYS_PER_TAB) return tabJourneys;

			// Sort by last_event_timestamp descending (keep most recent)
			const sorted = [...keys].sort((a, b) => {
				const aTime = tabJourneys[a]?.last_event_timestamp || 0;
				const bTime = tabJourneys[b]?.last_event_timestamp || 0;
				return bTime - aTime;
			});

			const pruned = {};
			for (let i = 0; i < MAX_ACTIVE_JOURNEYS_PER_TAB; i++) {
				const k = sorted[i];
				pruned[k] = tabJourneys[k];
			}
			return pruned;
		}

		/**
		 * Core Journey Resolution Algorithm (Part 3, 7, 8, 9, 10, 11, 12, 13, 14).
		 * Evaluates whether an incoming interaction continues an active journey,
		 * creates an auxiliary context, suspends for external gateway, or starts a new journey.
		 */
		resolveJourney(event, sender, sessionId, tabJourneysStorage = {}) {
			const now = Date.now();
			const tabId = sender?.tab?.id ?? event.tab_id ?? null;
			const tabKey = String(tabId);
			const url = event.url || sender?.tab?.url || '';
			const route = event.route || '';
			const currentSite = extractSiteIdentity(url);
			const productAnchor = extractProductAnchor(url, route, event.dom_context);

			// Check 1: Auxiliary Context (Privacy, Terms, FAQ, Help - Part 12)
			if (isAuxiliaryRoute(route) || isAuxiliaryRoute(url)) {
				const currentActive = this.getActiveJourney(tabJourneysStorage[tabKey]);
				const auxContext = this.createAuxiliaryContext(currentActive?.journey_id, route);
				// Suspend active journey if currently open
				if (currentActive && currentActive.status === STATUSES.ACTIVE) {
					currentActive.status = STATUSES.SUSPENDED;
				}
				return {
					journey_id: null,
					journey_stage: null,
					is_auxiliary: true,
					auxiliary_id: auxContext.auxiliary_id,
					action: 'AUXILIARY_CONTEXT'
				};
			}

			// Check 2: External Payment Gateway (Part 13)
			let host = '';
			try { host = new URL(url).hostname; } catch (e) { host = url.split('/')[0]; }
			if (isExternalPaymentGateway(host)) {
				const currentActive = this.getActiveJourney(tabJourneysStorage[tabKey]);
				if (currentActive && currentActive.status === STATUSES.ACTIVE) {
					currentActive.status = STATUSES.SUSPENDED_EXTERNAL_GATEWAY;
				}
				return {
					journey_id: null,
					journey_stage: null,
					is_auxiliary: false,
					action: 'SUSPENDED_EXTERNAL_GATEWAY'
				};
			}

			// Ensure tab journey map exists
			if (!tabJourneysStorage[tabKey]) {
				tabJourneysStorage[tabKey] = {};
			}
			const journeys = tabJourneysStorage[tabKey];

			// Find currently active journey in this tab
			let activeJourney = this.getActiveJourney(journeys);

			// Evaluate inactivity on active journey (Part 9)
			if (activeJourney) {
				const inactStatus = this.evaluateInactivity(activeJourney, now);
				if (inactStatus === STATUSES.EXPIRED_INACTIVE) {
					activeJourney.status = STATUSES.EXPIRED_INACTIVE;
					activeJourney = null; // Forces new journey creation
				} else if (inactStatus === STATUSES.IDLE) {
					activeJourney.status = STATUSES.IDLE;
				}
			}

			const inferredStage = inferStageFromRouteAndEvent(route, event.action, event.text, event.dom_context);
			const intentType = inferredStage.startsWith('CANCEL') || inferredStage === STAGES.RETENTION_STEP ? 'CANCELLATION' : 'PURCHASE';

			// Scenario A: No active journey exists in tab -> START NEW JOURNEY
			if (!activeJourney) {
				const newJourney = this.createJourney(tabId, sessionId, currentSite, intentType, inferredStage, productAnchor);
				journeys[newJourney.journey_id] = newJourney;
				tabJourneysStorage[tabKey] = this.pruneJourneys(journeys);
				return {
					journey_id: newJourney.journey_id,
					journey_stage: newJourney.journey_stage,
					is_auxiliary: false,
					action: 'STARTED_NEW_JOURNEY'
				};
			}

			// Scenario B: Active journey exists -> Evaluate continuity vs boundary break
			// Rule B.1: Site identity mismatch -> Breaks journey (Part 8)
			if (activeJourney.site_identity !== currentSite && activeJourney.site_identity !== 'unknown_site' && currentSite !== 'unknown_site') {
				activeJourney.status = STATUSES.ABANDONED;
				const newJourney = this.createJourney(tabId, sessionId, currentSite, intentType, inferredStage, productAnchor);
				journeys[newJourney.journey_id] = newJourney;
				tabJourneysStorage[tabKey] = this.pruneJourneys(journeys);
				return {
					journey_id: newJourney.journey_id,
					journey_stage: newJourney.journey_stage,
					is_auxiliary: false,
					action: 'STARTED_NEW_JOURNEY_SITE_MISMATCH'
				};
			}

			// Rule B.2: Returning from SUSPENDED or SUSPENDED_EXTERNAL_GATEWAY (Gate-2 Section 5 & I)
			if (activeJourney.status === STATUSES.SUSPENDED_EXTERNAL_GATEWAY) {
				const isConfirmation = inferredStage === STAGES.CONFIRMATION || /confirm|success|receipt|thank|order-complete/i.test(route || url);
				const isRetry = inferredStage === STAGES.PAYMENT || inferredStage === STAGES.CHECKOUT || /pay|retry|decline/i.test(route || url);
				const isHomeOrDiscovery = inferredStage === STAGES.DISCOVERY || route === '/' || route === '' || /shop|catalog|category/i.test(route || url);
				if (isConfirmation) {
					activeJourney.status = STATUSES.COMPLETED;
					activeJourney.journey_stage = STAGES.CONFIRMATION;
				} else if (isRetry) {
					activeJourney.status = STATUSES.ACTIVE;
					activeJourney.journey_stage = STAGES.PAYMENT;
				} else if (isHomeOrDiscovery) {
					activeJourney.status = STATUSES.IDLE;
				} else {
					activeJourney.status = STATUSES.ACTIVE;
				}
			} else if (activeJourney.status === STATUSES.SUSPENDED) {
				activeJourney.status = STATUSES.ACTIVE;
			} else if (activeJourney.status === STATUSES.IDLE) {
				activeJourney.status = STATUSES.ACTIVE; // Resumes soft idle
			}

			// Rule B.3: Check same-origin product browsing vs committed checkout (Gate-2 Section 3 & 7)
			const hasCommitment = activeJourney.journey_stage === STAGES.CART
				|| activeJourney.journey_stage === STAGES.CHECKOUT
				|| activeJourney.journey_stage === STAGES.PAYMENT;
			activeJourney.has_commitment = activeJourney.has_commitment || hasCommitment;

			if (activeJourney.product_anchor && productAnchor && activeJourney.product_anchor !== productAnchor) {
				if (!activeJourney.has_commitment && (inferredStage === STAGES.PRODUCT || inferredStage === STAGES.DISCOVERY)) {
					// Normal catalog browsing / comparison: update anchor, continue journey without abandonment
					activeJourney.product_anchor = productAnchor;
				} else if (activeJourney.has_commitment) {
					// Conflicting strong product anchor during checkout/cart commitment: record product mismatch anomaly
					activeJourney.product_mismatch_detected = true;
				}
			}

			// Rule B.4: Terminal Stage reached (CONFIRMATION / TERMINATION - Part 22)
			if (inferredStage === STAGES.CONFIRMATION || inferredStage === STAGES.TERMINATION) {
				activeJourney.journey_stage = inferredStage;
				activeJourney.stage_history.push(inferredStage);
				activeJourney.status = inferredStage === STAGES.CONFIRMATION ? STATUSES.COMPLETED : STATUSES.TERMINATED;
				activeJourney.last_event_timestamp = now;
				activeJourney.events_count = (activeJourney.events_count || 0) + 1;

				return {
					journey_id: activeJourney.journey_id,
					journey_stage: activeJourney.journey_stage,
					is_auxiliary: false,
					action: 'COMPLETED_TERMINAL_STAGE'
				};
			}

			// Rule B.5: SPA in-place stage transition check (Part 14)
			const spaTransition = evaluateSpaStageTransition(activeJourney.journey_stage, event, event.diff_signals);
			if (spaTransition) {
				activeJourney.journey_stage = spaTransition;
				activeJourney.stage_history.push(spaTransition);
			} else if (inferredStage !== STAGES.UNKNOWN && inferredStage !== activeJourney.journey_stage) {
				activeJourney.journey_stage = inferredStage;
				activeJourney.stage_history.push(inferredStage);
			}

			// Update product anchor if newly observed
			if (!activeJourney.product_anchor && productAnchor) {
				activeJourney.product_anchor = productAnchor;
			}

			activeJourney.last_event_timestamp = now;
			activeJourney.events_count = (activeJourney.events_count || 0) + 1;

			return {
				journey_id: activeJourney.journey_id,
				journey_stage: activeJourney.journey_stage,
				is_auxiliary: false,
				action: 'CONTINUED_CURRENT_JOURNEY'
			};
		}

		/**
		 * Retrieve active non-terminal journey for a tab (Part 3 & 7).
		 */
		getActiveJourney(tabJourneys) {
			if (!tabJourneys || typeof tabJourneys !== 'object') return null;
			for (const jid of Object.keys(tabJourneys)) {
				const j = tabJourneys[jid];
				if (j && !TERMINAL_STATUSES.has(j.status)) {
					return j;
				}
			}
			return null;
		}

		getOrCreateJourney(tabId, url, sessionId, nowMs, options = {}) {
			const now = nowMs || Date.now();
			const tabKey = String(tabId);
			if (!this.tabStorage[tabKey]) {
				this.tabStorage[tabKey] = {};
			}
			const journeys = this.tabStorage[tabKey];
			let active = this.getActiveJourney(journeys);

			if (active) {
				const inact = this.evaluateInactivity(active, now);
				if (inact === STATUSES.EXPIRED_INACTIVE) {
					active.status = STATUSES.EXPIRED_INACTIVE;
					active = null;
				} else if (inact === STATUSES.IDLE) {
					active.status = STATUSES.IDLE;
				}
			}

			const currentSite = extractSiteIdentity(url);
			const stage = this.inferStageFromRoute(url);
			const intent = options.intent || (stage.startsWith('CANCEL') || stage === STAGES.RETENTION_STEP ? 'CANCELLATION' : 'PURCHASE');
			const productAnchor = options.productAnchor || extractProductAnchor(url, '', null);

			if (!active) {
				const newJ = this.createJourney(tabId, sessionId, currentSite, intent, stage, productAnchor);
				newJ.created_timestamp = now;
				newJ.last_event_timestamp = now;
				journeys[newJ.journey_id] = newJ;
				this.tabStorage[tabKey] = this.pruneJourneys(journeys);
				return newJ;
			}

			// Check site mismatch
			if (active.site_identity !== currentSite && active.site_identity !== 'unknown_site' && currentSite !== 'unknown_site') {
				active.status = STATUSES.ABANDONED;
				const newJ = this.createJourney(tabId, sessionId, currentSite, intent, stage, productAnchor);
				newJ.created_timestamp = now;
				newJ.last_event_timestamp = now;
				journeys[newJ.journey_id] = newJ;
				this.tabStorage[tabKey] = this.pruneJourneys(journeys);
				return newJ;
			}

			// Check intent change on same route
			if (options.intent && options.intent !== active.intent_type) {
				active.status = STATUSES.ABANDONED;
				const newJ = this.createJourney(tabId, sessionId, currentSite, options.intent, stage, productAnchor);
				newJ.created_timestamp = now;
				newJ.last_event_timestamp = now;
				journeys[newJ.journey_id] = newJ;
				this.tabStorage[tabKey] = this.pruneJourneys(journeys);
				return newJ;
			}

			// Resumes if idle
			if (active.status === STATUSES.IDLE) {
				active.status = STATUSES.ACTIVE;
			}
			active.last_event_timestamp = now;
			return active;
		}

		getJourneysForTab(tabId) {
			const tabKey = String(tabId);
			return Object.values(this.tabStorage[tabKey] || {});
		}

		completeJourney(journeyId) {
			for (const tabKey of Object.keys(this.tabStorage)) {
				if (this.tabStorage[tabKey][journeyId]) {
					this.tabStorage[tabKey][journeyId].status = STATUSES.COMPLETED;
					return true;
				}
			}
			return false;
		}

		abandonJourney(journeyId) {
			for (const tabKey of Object.keys(this.tabStorage)) {
				if (this.tabStorage[tabKey][journeyId]) {
					this.tabStorage[tabKey][journeyId].status = STATUSES.ABANDONED;
					return true;
				}
			}
			return false;
		}

		terminateJourney(journeyId) {
			for (const tabKey of Object.keys(this.tabStorage)) {
				if (this.tabStorage[tabKey][journeyId]) {
					this.tabStorage[tabKey][journeyId].status = STATUSES.TERMINATED;
					return true;
				}
			}
			return false;
		}

		handleAuxiliaryNavigation(tabId, url, sessionId) {
			const tabKey = String(tabId);
			const journeys = this.tabStorage[tabKey] || {};
			const active = this.getActiveJourney(journeys);
			if (active && active.status === STATUSES.ACTIVE) {
				active.status = STATUSES.SUSPENDED;
			}
			return this.createAuxiliaryContext(active?.journey_id, url);
		}

		handleExternalPaymentGateway(tabId, gatewayUrl) {
			return this.handleExternalGatewayNavigation(tabId, gatewayUrl);
		}

		handleExternalGatewayNavigation(tabId, gatewayUrl, nowMs) {
			const tabKey = String(tabId);
			const journeys = this.tabStorage[tabKey] || {};
			const active = this.getActiveJourney(journeys);
			if (active) {
				active.status = STATUSES.SUSPENDED_EXTERNAL_GATEWAY;
				if (nowMs) active.last_event_timestamp = nowMs;
				return { suspended: true, journey_id: active.journey_id };
			}
			return { suspended: false, journey_id: null };
		}

		resumeFromGatewayReturn(tabId, returnUrl) {
			const tabKey = String(tabId);
			const journeys = this.tabStorage[tabKey] || {};
			const active = this.getActiveJourney(journeys);
			if (!active || active.status !== STATUSES.SUSPENDED_EXTERNAL_GATEWAY) {
				return null;
			}
			const site = extractSiteIdentity(returnUrl);
			if (site === active.site_identity || active.site_identity === 'unknown_site') {
				active.status = STATUSES.ACTIVE;
				active.last_event_timestamp = Date.now();
				return active;
			}
			return null;
		}

		evaluateStatus(journeyId, nowMs) {
			for (const tabKey of Object.keys(this.tabStorage)) {
				const j = this.tabStorage[tabKey][journeyId];
				if (j) {
					return this.evaluateInactivity(j, nowMs);
				}
			}
			return STATUSES.UNKNOWN;
		}

		inferStageFromRoute(route) {
			return inferStageFromRouteAndEvent(route, null, null, null);
		}

		evaluateSPATransition(journey, signals) {
			let count = 0;
			if (signals.domLandmarkChanged) count++;
			if (signals.userAction) count++;
			if (signals.formSignatureChanged) count++;
			return count >= 2;
		}

		recordSPATransition(journey, targetStage, signals, nowMs) {
			if (!this.evaluateSPATransition(journey, signals)) {
				return false;
			}
			const now = nowMs || Date.now();
			if (journey.last_spa_transition_ts && (now - journey.last_spa_transition_ts < 1500)) {
				return false; // Debounce 1.5s settle window
			}
			journey.last_spa_transition_ts = now;
			journey.journey_stage = targetStage;
			if (!journey.stage_history.includes(targetStage)) {
				journey.stage_history.push(targetStage);
			}
			return true;
		}

		recordEvent(journeyId, event) {
			if (!this.eventHistory[journeyId]) {
				this.eventHistory[journeyId] = [];
			}
			// Sanitize sensitive values (Part 24)
			const sanitized = {};
			const sensitive = new Set(['password', 'cardnumber', 'card_number', 'card', 'cvv', 'cvc', 'pin', 'ssn', 'token', 'auth']);
			for (const [k, v] of Object.entries(event || {})) {
				if (!sensitive.has(k.toLowerCase())) {
					sanitized[k] = v;
				}
			}
			this.eventHistory[journeyId].push(sanitized);
			// Prune bounded events
			if (this.eventHistory[journeyId].length > MAX_EVENTS_PER_JOURNEY) {
				this.eventHistory[journeyId] = this.eventHistory[journeyId].slice(-MAX_EVENTS_PER_JOURNEY);
			}
		}

		getEvents(journeyId) {
			return this.eventHistory[journeyId] || [];
		}
	}

	return {
		JourneyManager,
		makeJourneyId,
		makeAuxiliaryId,
		extractSiteIdentity,
		isExternalPaymentGateway,
		isAuxiliaryRoute,
		extractProductAnchor,
		inferStageFromRouteAndEvent,
		evaluateSpaStageTransition,
		STAGES,
		STATUSES,
		TERMINAL_STATUSES,
		JOURNEY_INACTIVITY_TIMEOUT_MS,
		JOURNEY_SOFT_IDLE_TIMEOUT_MS,
		MAX_ACTIVE_JOURNEYS_PER_TAB,
		MAX_EVENTS_PER_JOURNEY
	};
}));
