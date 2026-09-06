import type { PhoneContact } from '@/lib/types';

export default function PhoneLinks({ phone, contacts, variant = 'inline' }: { phone: string; contacts?: PhoneContact[]; variant?: 'inline' | 'action' }) {
  // Older API responses keep their source text; never concatenate or guess a dial number.
  return <span className={`phone-links${variant === 'action' ? ' phone-links--action' : ''}`}>{contacts?.length ? contacts.map((contact, index) =>
    contact.dial && /^0\d{1,2}-\d{3,4}-\d{4}$/.test(contact.dial) ?
      <a key={index} href={`tel:${contact.dial}`} aria-label={`${contact.label} 전화 ${contact.dial}`}>{variant === 'action' ? `전화 ${contact.dial}` : contact.label}</a> :
      <span key={index}>{contact.label}</span>) : phone}</span>;
}
