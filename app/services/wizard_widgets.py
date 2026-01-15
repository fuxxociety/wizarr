"""
Wizard widget system for embedding dynamic content in wizard steps.

Widgets are inserted into markdown content using special syntax:
{{ widget:recently_added_media }}
{{ widget:recently_added_media limit=6 }}
{{ widget:button url="https://example.com" text="Click Here" }}

Cards use delimiter syntax:
|||
# Card Title
This is the card content with **markdown** support.
|||
"""

import logging
import re
from typing import Any

import markdown
from flask import render_template_string

from app.services.media.service import get_media_client


class WizardWidget:
    """Base class for wizard widgets."""

    def __init__(self, name: str, template: str):
        self.name = name
        self.template = template

    def render(self, server_type: str, _context: dict | None = None, **kwargs) -> str:
        """Render the widget with given parameters."""
        try:
            data = self.get_data(server_type, **kwargs)
            html_content = render_template_string(self.template, **data)
            # Wrap in markdown HTML block to ensure it's treated as raw HTML
            return f'\n\n<div class="widget-container">\n{html_content}\n</div>\n\n'
        except Exception:
            # Fail gracefully in wizard context
            return f'\n\n<div class="text-sm text-gray-500 italic">Widget "{self.name}" temporarily unavailable</div>\n\n'

    def get_data(self, _server_type: str, **_kwargs) -> dict[str, Any]:
        """Override this method to provide data for the widget."""
        return {}


class RecentlyAddedMediaWidget(WizardWidget):
    """Widget to show recently added media from the server."""

    def __init__(self):
        template = """
        <div class="media-carousel-widget my-6">
            {% if items %}
            <div class="carousel-container overflow-hidden relative">
                <div class="carousel-track flex animate-scroll gap-3" style="width: {{ (items|length * 2) * 150 }}px;">
                    {% for item in items %}
                    <div class="carousel-item flex-shrink-0">
                        {% if item.thumb %}
                        <img src="{{ item.thumb }}" alt="{{ item.title }}"
                             loading="lazy"
                             decoding="async"
                             class="w-32 h-48 object-cover rounded-lg shadow-lg hover:shadow-xl transition-shadow duration-300">
                        {% else %}
                        <div class="w-32 h-48 bg-gradient-to-br from-primary/20 to-primary/40 rounded-lg shadow-lg flex items-center justify-center">
                            <svg class="w-8 h-8 text-primary" fill="currentColor" viewBox="0 0 20 20">
                                <path d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2H4zm12 12H4l4-8 3 6 2-4 3 6z"/>
                            </svg>
                        </div>
                        {% endif %}
                    </div>
                    {% endfor %}
                    <!-- Duplicate items for seamless loop -->
                    {% for item in items %}
                    <div class="carousel-item flex-shrink-0">
                        {% if item.thumb %}
                        <img src="{{ item.thumb }}" alt="{{ item.title }}"
                             loading="lazy"
                             decoding="async"
                             class="w-32 h-48 object-cover rounded-lg shadow-lg hover:shadow-xl transition-shadow duration-300">
                        {% else %}
                        <div class="w-32 h-48 bg-gradient-to-br from-primary/20 to-primary/40 rounded-lg shadow-lg flex items-center justify-center">
                            <svg class="w-8 h-8 text-primary" fill="currentColor" viewBox="0 0 20 20">
                                <path d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 00-2-2H4zm12 12H4l4-8 3 6 2-4 3 6z"/>
                            </svg>
                        </div>
                        {% endif %}
                    </div>
                    {% endfor %}
                </div>
            </div>

            <style>
            @keyframes scroll {
                0% {
                    transform: translateX(0);
                }
                100% {
                    transform: translateX(-50%);
                }
            }

            .animate-scroll {
                animation: scroll 30s linear infinite;
            }

            .carousel-container:hover .animate-scroll {
                animation-play-state: paused;
            }
            </style>
            {% else %}
            <div class="text-center py-8 text-gray-500 dark:text-gray-400">
                <svg class="w-12 h-12 mx-auto mb-2 text-gray-300" fill="currentColor" viewBox="0 0 20 20">
                    <path d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2H4zm12 12H4l4-8 3 6 2-4 3 6z"/>
                </svg>
                <p class="text-sm">{{ _("No recent content available") }}</p>
            </div>
            {% endif %}
        </div>
        """
        super().__init__("recently_added_media", template)

    def get_data(self, server_type: str, **kwargs) -> dict[str, Any]:
        """Fetch recently added media from the server."""
        limit = kwargs.get("limit", 6)

        try:
            # Get media client for the server type
            from app.models import MediaServer

            server = MediaServer.query.filter_by(server_type=server_type).first()

            if not server:
                # Try to get any server if none match the exact type
                server = MediaServer.query.first()

            if not server:
                return {"items": [], "limit": limit}

            client = get_media_client(server.server_type, server)

            if not client:
                return {"items": [], "limit": limit}

            # Get recently added items
            recent_items = self._get_recent_items(client, limit)

            return {"items": recent_items, "limit": limit}

        except Exception:
            # Return empty data on any error to fail gracefully
            return {"items": [], "limit": limit}

    def _get_recent_items(self, client, limit: int):
        """Extract recent items from media client."""
        try:
            # Use the new get_recent_items method if available
            if hasattr(client, "get_recent_items"):
                return client.get_recent_items(limit=limit)

            # Fallback: try to get recent content from libraries
            libraries = client.libraries()
            recent_items = []

            # For each library, try to get recent content
            for library in libraries[:3]:  # Limit to first 3 libraries
                try:
                    if hasattr(client, "get_recent_items"):
                        items = client.get_recent_items(library.get("id"), limit=2)
                        recent_items.extend(items)
                except Exception as exc:
                    logging.debug(
                        f"Failed to get recent items for library {library.get('id')}: {exc}"
                    )
                    continue

            return recent_items[:limit]

        except Exception:
            return []


class CardWidget(WizardWidget):
    """Widget to create a card - not used with standard widget syntax, rendered via delimiter."""

    def __init__(self):
        # Placeholder - cards are handled by process_card_delimiters
        super().__init__("card", "")

    def render(self, _server_type: str, **_kwargs) -> str:
        """Cards should use delimiter syntax instead."""
        return '\n\n<div class="text-sm text-yellow-500 italic">Use ||| delimiter syntax for cards instead</div>\n\n'


class ButtonWidget(WizardWidget):
    """Widget to create a standard Wizarr button with a link."""

    def __init__(self):
        # Empty template since we'll override render
        super().__init__("button", "")

    def render(self, _server_type: str, context: dict | None = None, **kwargs) -> str:
        """Render the button widget with direct HTML generation."""
        try:
            import html

            url = kwargs.get("url", "")
            text = kwargs.get("text", "Click Here")
            context = context or {}

            # If URL is a Jinja variable name (no protocol and no slashes), try to resolve it from context
            if (
                url
                and not url.startswith(("http://", "https://", "//", "{{"))
                and "/" not in url
            ):
                # First try to get it from context directly
                if url in context:
                    url = context[url]
                else:
                    # Try to render it as a Jinja variable
                    try:
                        from flask_babel import gettext as _translate

                        render_ctx = context.copy()
                        render_ctx["_"] = _translate
                        url = render_template_string(f"{{{{ {url} }}}}", **render_ctx)
                    except Exception as exc:
                        # If rendering fails, keep original value
                        logging.debug(f"Failed to render URL template '{url}': {exc}")

            # If text contains translation function call, render it first
            text_str = str(text)

            if "_(" in text_str:
                try:
                    # Import gettext to make it available in the template context
                    from flask_babel import gettext as _translate

                    # Wrap _("...") in {{ }} to make it a Jinja expression
                    template_str = f"{{{{ {text_str} }}}}"
                    text = render_template_string(template_str, _=_translate)
                except Exception as exc:
                    # If rendering fails, use the text as-is
                    logging.debug(
                        f"Failed to render text translation '{text_str}': {exc}"
                    )
            elif "{{" in text_str:
                # Already has Jinja syntax, render as-is
                try:
                    from flask_babel import gettext as _translate

                    text = render_template_string(text_str, _=_translate)
                except Exception as exc:
                    # If rendering fails, use the text as-is
                    logging.debug(f"Failed to render text template '{text_str}': {exc}")

            # Ensure URL has proper protocol if missing
            if url and not url.startswith(("http://", "https://", "//")) and "." in url:
                # If it looks like a domain, prepend https://
                url = f"https://{url}"

            # Validate required parameters after processing
            if not url:
                # Empty URL means server not configured - hide button gracefully
                return ""

            if not text:
                return '\n\n<div class="text-sm text-red-500 italic">Button widget requires text parameter</div>\n\n'

            # Escape for safety
            escaped_text = html.escape(text)
            escaped_url = html.escape(url)

            # Generate button HTML
            return f'''
<div class="flex justify-center w-full my-6">
<div class="inline-flex">
    <a href="{escaped_url}" class="inline-flex items-center px-6 py-3 text-base font-medium text-white bg-primary rounded-lg hover:bg-primary-hover focus:ring-4 focus:ring-primary-300 dark:bg-primary-600 dark:hover:bg-primary dark:focus:ring-primary-800 transition-colors duration-200" style="text-decoration: none;" target="_blank" rel="noopener noreferrer">
        {escaped_text}
    </a>
</div>
</div>
'''

        except Exception as e:
            return f'\n\n<div class="text-sm text-gray-500 italic">Button widget error: {e}</div>\n\n'


class StripePaymentWidget(WizardWidget):
    """Widget to display Stripe Checkout Embedded Form for payment during wizard."""

    def __init__(self):
        template = """
        <div class="stripe-payment-widget my-6">
            {% if stripe_configured %}
                <div class="space-y-4">
                    <!-- Debug info (remove after testing) -->
                    <div class="text-xs text-gray-500 bg-gray-100 p-2 rounded hidden">
                        PublicKey: {{ stripe_public_key[:10] if stripe_public_key else 'EMPTY' }}...
                        Code: {{ invitation_code[:10] if invitation_code else 'EMPTY' }}...
                        Endpoint: {{ get_payment_intent_url }}
                    </div>

                    <!-- Stripe Checkout Embedded Form Container -->
                    <div id="checkout-element-container" class="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-6">
                        <!-- Embedded form will be loaded here -->
                    </div>

                    <!-- Payment Status Messages -->
                    <div id="payment-message" class="mt-4 hidden">
                        <div id="payment-status-content"></div>
                    </div>

                    <!-- Error Messages -->
                    <div id="payment-error" class="mt-4 hidden">
                        <div class="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
                            <p id="error-message" class="text-red-800 dark:text-red-200 text-sm"></p>
                        </div>
                    </div>

                    <!-- Loading State -->
                    <div id="payment-loading" class="mt-4 hidden">
                        <div class="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                            <div class="flex items-center">
                                <svg class="animate-spin h-5 w-5 text-blue-600 dark:text-blue-400 mr-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                                <span class="text-blue-800 dark:text-blue-200">{{ _("Processing your payment...") }}</span>
                            </div>
                        </div>
                    </div>
                </div>

                <script src="https://js.stripe.com/v3/"></script>
                <script>
                console.log('Stripe Payment Widget Script Starting');
                console.log('Public Key:', '{{ stripe_public_key }}' ? '{{ stripe_public_key }}'.substring(0, 10) + '...' : 'EMPTY');
                console.log('Invitation Code:', '{{ invitation_code }}' ? '{{ invitation_code }}'.substring(0, 10) + '...' : 'EMPTY');
                console.log('Intent Endpoint:', '{{ get_payment_intent_url }}');

                // Initialize Stripe
                const stripe = Stripe('{{ stripe_public_key }}');
                let elements = null;
                let paymentElement = null;

                async function initializeCheckout() {
                    try {
                        console.log('initializeCheckout called');

                        // Fetch client secret from backend
                        const response = await fetch('{{ get_payment_intent_url }}', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify({
                                invitation_code: '{{ invitation_code }}'
                            })
                        });

                        console.log('Fetch response:', response.status, response.ok);

                        if (!response.ok) {
                            const errorData = await response.text();
                            console.error('API Error:', errorData);
                            throw new Error('Failed to initialize payment');
                        }

                        const data = await response.json();
                        console.log('API Response:', data);

                        const clientSecret = data.client_secret;

                        if (!clientSecret) {
                            console.error('No client secret in response');
                            throw new Error('No client secret received');
                        }

                        console.log('Creating elements with clientSecret:', clientSecret.substring(0, 20) + '...');

                        // Create Elements instance
                        elements = stripe.elements({
                            clientSecret: clientSecret,
                            appearance: {
                                theme: document.documentElement.classList.contains('dark') ? 'night' : 'stripe',
                                variables: {
                                    colorPrimary: 'var(--color-primary, #3b82f6)',
                                    colorBackground: document.documentElement.classList.contains('dark') ? '#1f2937' : '#ffffff',
                                    colorText: document.documentElement.classList.contains('dark') ? '#f3f4f6' : '#1f2937',
                                    fontFamily: 'system-ui, -apple-system, sans-serif'
                                }
                            }
                        });

                        console.log('Elements created, creating payment element');

                        // Mount Payment Element
                        paymentElement = elements.create('payment');
                        paymentElement.mount('#checkout-element-container');

                        console.log('Payment element mounted');

                        // Create payment form
                        const form = document.createElement('form');
                        form.id = 'payment-form';
                        form.className = 'mt-6';
                        form.innerHTML = `
                            <button type="submit" class="w-full px-4 py-3 bg-primary hover:bg-primary-hover text-white font-medium rounded-lg transition-colors">
                                {{ _("Complete Payment") }}
                            </button>
                        `;

                        const container = document.getElementById('checkout-element-container');
                        container.parentElement.insertBefore(form, container.nextSibling);

                        // Handle form submission
                        form.addEventListener('submit', handleSubmit);
                        console.log('Form listener attached');

                    } catch (error) {
                        console.error('Checkout initialization error:', error);
                        showError(error.message || '{{ _("Payment initialization failed") }}');
                    }
                }

                async function handleSubmit(e) {
                    e.preventDefault();
                    console.log('Form submitted');

                    if (!elements) {
                        showError('{{ _("Payment form not initialized") }}');
                        return;
                    }

                    showLoading(true);

                    try {
                        // Confirm payment with Stripe
                        console.log('Confirming payment...');
                        const { error: submitError } = await stripe.confirmPayment({
                            elements: elements,
                            confirmParams: {
                                return_url: '{{ payment_return_url }}'
                            }
                        });

                        if (submitError) {
                            console.error('Submit error:', submitError);
                            showError(submitError.message);
                            showLoading(false);
                        } else {
                            console.log('Payment confirmed, redirecting...');
                        }
                        // If no error, stripe will redirect to return_url
                    } catch (error) {
                        console.error('Payment submission error:', error);
                        showError(error.message || '{{ _("Payment processing failed") }}');
                        showLoading(false);
                    }
                }

                function showError(message) {
                    console.log('Showing error:', message);
                    const errorDiv = document.getElementById('payment-error');
                    const errorMessage = document.getElementById('error-message');
                    errorMessage.textContent = message;
                    errorDiv.classList.remove('hidden');
                    document.getElementById('payment-message').classList.add('hidden');
                }

                function showLoading(show) {
                    console.log('Setting loading state:', show);
                    document.getElementById('payment-loading').classList.toggle('hidden', !show);
                    const submitButton = document.getElementById('payment-form')?.querySelector('button');
                    if (submitButton) {
                        submitButton.disabled = show;
                    }
                }

                // Initialize when page loads
                console.log('Adding DOMContentLoaded listener');
                document.addEventListener('DOMContentLoaded', initializeCheckout);

                // Also try to initialize immediately in case DOM is already loaded
                if (document.readyState === 'loading') {
                    console.log('DOM still loading');
                } else {
                    console.log('DOM already loaded, initializing immediately');
                    initializeCheckout();
                }
            {% else %}
            <div class="text-center py-8 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
                <svg class="w-12 h-12 mx-auto mb-2 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/>
                </svg>
                <p class="text-red-600 dark:text-red-200 font-medium">{{ error_message or _("Stripe not configured") }}</p>
                <p class="text-sm text-red-500 dark:text-red-300 mt-2">{{ _("Please contact support") }}</p>
            </div>
            {% endif %}
        </div>
        """
        super().__init__("stripe_payment", template)

    def get_data(self, _server_type: str, **kwargs) -> dict[str, Any]:
        """Fetch Stripe configuration for Checkout Embedded Form."""
        from flask import has_request_context, url_for, session
        from app.models import Settings
        import logging

        try:
            # Check if Stripe is configured
            settings_dict = {s.key: s.value for s in Settings.query.all()}
            stripe_connected = settings_dict.get("stripe_connected") in ["True", "true", "1", True]

            if not stripe_connected:
                logging.warning("Stripe not connected in get_data")
                return {
                    "stripe_configured": False,
                    "stripe_public_key": "",
                    "get_payment_intent_url": "",
                    "payment_return_url": "",
                    "invitation_code": "",
                    "error_message": "Stripe is not connected"
                }

            # Get Stripe configuration
            from app.services.stripe_service import StripeService

            if not StripeService.is_configured():
                logging.warning("Stripe service not configured in get_data")
                return {
                    "stripe_configured": False,
                    "stripe_public_key": "",
                    "get_payment_intent_url": "",
                    "payment_return_url": "",
                    "invitation_code": "",
                    "error_message": "Stripe service not configured"
                }

            # Get Stripe publishable key from settings
            stripe_publishable_key = settings_dict.get("stripe_publishable_key", "")
            if not stripe_publishable_key:
                # Fallback: try to get from environment
                import os
                stripe_publishable_key = os.getenv("STRIPE_PUBLISHABLE_KEY", "")

            # If still empty, we have a problem - need to log and fail
            if not stripe_publishable_key:
                logging.error("Stripe publishable key not found in settings or environment!")
                return {
                    "stripe_configured": False,
                    "stripe_public_key": "",
                    "get_payment_intent_url": "",
                    "payment_return_url": "",
                    "invitation_code": "",
                    "error_message": "Stripe publishable key not configured. Please check admin settings."
                }

            # Get invitation code from session
            from app.services.invite_code_manager import InviteCodeManager
            invitation_code = ""
            get_payment_intent_url = "/wizard/get-payment-intent"
            payment_return_url = "/wizard/payment-complete"

            if has_request_context():
                invitation_code = InviteCodeManager.get_invite_code() or ""
                # Debug: also check session directly
                if not invitation_code:
                    invitation_code = session.get("wizard_access", "")

                get_payment_intent_url = url_for("wizard.get_payment_intent", _external=False)
                payment_return_url = url_for("wizard.payment_complete", _external=True)

            data = {
                "stripe_configured": True,
                "stripe_public_key": stripe_publishable_key,
                "get_payment_intent_url": get_payment_intent_url,
                "payment_return_url": payment_return_url,
                "invitation_code": invitation_code,
                "error_message": ""
            }

            logging.info(f"Stripe widget data: configured=True, public_key={stripe_publishable_key[:10] if stripe_publishable_key else 'EMPTY'}..., endpoint={get_payment_intent_url}, code={invitation_code[:10] if invitation_code else 'EMPTY'}...")
            return data

        except Exception as e:
            import logging
            logging.error(f"Error configuring Stripe Checkout: {e}", exc_info=True)
            return {
                "stripe_configured": False,
                "stripe_public_key": "",
                "get_payment_intent_url": "",
                "payment_return_url": "",
                "invitation_code": "",
                "error_message": str(e)
            }


# Widget registry
WIDGET_REGISTRY = {
    "recently_added_media": RecentlyAddedMediaWidget(),
    "button": ButtonWidget(),
    "stripe_payment": StripePaymentWidget(),
}


def process_card_delimiters(content: str) -> str:
    """
    Process card delimiters (|||) and convert to styled cards.

    Example:
    |||
    # Card Title
    This is content
    |||
    """

    def replace_card(match):
        card_content = match.group(1).strip()

        if not card_content:
            return '<div class="text-sm text-red-500 italic">Empty card content</div>'

        try:
            # Convert markdown to HTML
            html_content = markdown.markdown(
                card_content, extensions=["extra", "nl2br"]
            )

            # Wrap in card styling with extra bottom margin for spacing between cards
            return f"""<div class="card-widget my-6 mb-8 rounded-xl border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-800 p-5 sm:p-6">
    <div class="prose prose-sm dark:prose-invert max-w-none">
        {html_content}
    </div>
</div>"""

        except Exception as e:
            return f'<div class="text-sm text-red-500 italic">Card rendering error: {e}</div>'

    # Match ||| ... ||| patterns
    pattern = r"\|\|\|\s*\n(.*?)\n\s*\|\|\|"
    return re.sub(pattern, replace_card, content, flags=re.DOTALL)


def process_widget_placeholders(
    content: str, server_type: str, context: dict | None = None
) -> str:
    """
    Process widget placeholders in markdown content.

    Supports syntax like:
    {{ widget:recently_added_media }}
    {{ widget:recently_added_media limit=6 }}
    {{ widget:button url="https://example.com" text="Click Here" }}
    """
    context = context or {}

    def replace_widget(match):
        full_match = match.group(0)
        widget_call = match.group(1).strip()

        # Parse widget call
        if not widget_call.startswith("widget:"):
            return full_match

        # Remove 'widget:' prefix
        widget_spec = widget_call[7:]  # len('widget:') = 7

        # Split on first space to separate widget name from parameters
        parts = widget_spec.split(None, 1)
        widget_name = parts[0]

        # Parse parameters if present
        params = {}
        if len(parts) > 1:
            param_string = parts[1]

            # Match key="value" or key=_("value") or key=value patterns
            # This regex handles:
            # 1. Quoted values: key="value with spaces"
            # 2. Function calls with quoted args: key=_("translated text")
            # 3. Unquoted values: key=123
            param_pattern = r'(\w+)=(?:"([^"]*)"|(\w+\([^)]+\))|(\S+))'

            for param_match in re.finditer(param_pattern, param_string):
                key = param_match.group(1)
                # Use quoted value if present, otherwise function call, otherwise unquoted value
                value = (
                    param_match.group(2)
                    if param_match.group(2) is not None
                    else param_match.group(3)
                    if param_match.group(3) is not None
                    else param_match.group(4)
                )

                # Try to convert to int if possible
                from contextlib import suppress

                with suppress(ValueError):
                    value = int(value)

                params[key] = value

        # Get widget and render
        widget = WIDGET_REGISTRY.get(widget_name)
        if widget:
            return widget.render(server_type, context=context, **params)
        return f'<div class="text-sm text-red-500">Unknown widget: {widget_name}</div>'

    # Match {{ widget:... }} patterns specifically (not other {{ }} expressions)
    pattern = r"\{\{\s*(widget:[^}]+)\s*\}\}"
    return re.sub(pattern, replace_widget, content)
