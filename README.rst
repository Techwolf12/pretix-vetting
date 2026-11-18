Vetting
=======

This is a plugin for `pretix`_.

Lets existing attendees vouch for people who want to join an event. Orders for the selected products stay pending
approval until enough attendees have vouched for the applicant.

Configure it under *Settings → Vetting* in your event. The products you select must require approval.

There are two ways to vouch, and you can enable either or both:

* **References**: during checkout, applicants enter the email addresses of people attending who know them. If an
  address belongs to an attendee who is allowed to vouch, that person gets an email with a link where they answer
  "I vouch for them", "I don't vouch for them" or "I don't know them". Addresses that don't match anyone are accepted
  without telling the applicant, so the checkout can't be used to find out who is attending. Organizers see them in the
  backend.
* **Invites**: once their own vetted order is approved, attendees get invite codes on their order page. Someone who
  orders with one of these codes counts as vouched for by the attendee who handed it out.

You choose who can vouch (approved attendees of this event, attendees of the organizer's past events, or both),
whether they need to have paid, and optionally which products allow vouching. When enough people vouched, the order is
either approved automatically or the application is marked as ready for you. When someone doesn't vouch, the
application is either held for you to review or, after a number of negative answers, denied. You can always approve or
deny an order yourself.

To let someone in without vetting, create a voucher and tick *Skip vetting* (also available when creating vouchers in
bulk). Orders that use such a voucher for every product that needs vetting skip the vetting step at checkout and are
approved right away, unless something else in the order still needs approval.

Unanswered requests get a reminder and expire after a configurable number of days. Expiry needs pretix's periodic
task (``runperiodic``) to run.

The backend shows the vouches on each order and lists all open applications under *Vetting* in the event navigation.
Applicants only see how many vouches they have received, never who declined.

Development setup
-----------------

1. Make sure that you have a working `pretix development setup`_.

2. Clone this repository.

3. Activate the virtual environment you use for pretix development.

4. Execute ``python setup.py develop`` within this directory to register this application with pretix's plugin registry.

5. Execute ``make`` within this directory to compile translations.

6. Restart your local pretix server. You can now use the plugin from this repository for your events by enabling it in
   the 'plugins' tab in the settings.

This plugin has CI set up to enforce a few code style rules. To check locally, you need these packages installed::

    pip install flake8 isort black docformatter

To check your plugin for rule violations, run::

    docformatter --check -r .
    black --check .
    isort -c .
    flake8 .

You can auto-fix some of these issues by running::

    docformatter -r .
    isort .
    black .

To automatically check for these issues before you commit, you can run ``.install-hooks``.


License
-------

Copyright 2026 Christiaan de Die le Clercq (techwolf12)

Released under the terms of the Apache License 2.0


.. _pretix: https://github.com/pretix/pretix
.. _pretix development setup: https://docs.pretix.eu/en/latest/development/setup.html
