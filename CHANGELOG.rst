Changelog
=========

0.1.0 (2026-11-18)
------------------

First release.

- Hold orders for selected products until existing attendees vouch for the
  applicant. The products must require approval.
- References: applicants name attendees by email during checkout, and those
  attendees answer by email link whether they vouch for them. The checkout
  never reveals whether an address belongs to an attendee.
- Invites: approved attendees get invite codes on their order page. An order
  placed with a code counts as a vouch.
- Choose who can vouch: approved attendees of the event, attendees of the
  organizer's past events, or both. Optionally only paid orders, only holders
  of certain products, and a limit per attendee.
- When enough people vouch, approve the order automatically or only mark it
  for the organizer. A negative answer either holds the application for review
  or, after a set number, denies the order.
- Reminders and expiry for unanswered requests (needs pretix's periodic task).
- Vouches on the backend order page and the approval page, with a button to
  resend a request, and a *Vetting* list of open applications.
- Vouchers can skip vetting, also when created in bulk.
- German translations (formal and informal).
