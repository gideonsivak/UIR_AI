import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import People from './pages/People';
import PlantCheck from './pages/PlantCheck';
import MyPlants from './pages/MyPlants';

export default function App() { return <Layout><Routes><Route path="/" element={<People />} /><Route path="/plant-check" element={<PlantCheck />} /><Route path="/my-plants" element={<MyPlants />} /></Routes></Layout>; }
