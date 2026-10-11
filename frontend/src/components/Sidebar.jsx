import { NavLink } from 'react-router-dom';
import { Users, ScanSearch, Sprout } from 'lucide-react';
const links = [{ to: '/', label: 'People', icon: Users }, { to: '/plant-check', label: 'Plant Check', icon: ScanSearch }, { to: '/my-plants', label: 'My Plants', icon: Sprout }];
export default function Sidebar() { return <aside className="sidebar"><div className="brand"><Sprout aria-hidden="true" /><span>GIDEON <b>PLANT</b></span></div><nav aria-label="Main navigation">{links.map(({to,label,icon: Icon}) => <NavLink key={to} to={to} end={to === '/'}><Icon size={20} />{label}</NavLink>)}</nav><p className="sidebar-note">Better care, one plant at a time.</p></aside>; }
