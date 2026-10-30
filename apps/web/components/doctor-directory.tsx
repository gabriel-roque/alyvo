"use client";

import { ArrowRight, MapPin } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import type { Doctor } from "@alyvo/contracts";
import { apiFetch } from "@/lib/api";

export function DoctorDirectory() {
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  useEffect(() => {
    void apiFetch("/directory/doctors")
      .then((response) => response.json())
      .then((payload) => setDoctors(payload.items));
  }, []);
  return <div className="doctor-grid">
    {doctors.map((doctor) => (
      <article className="doctor-card" key={doctor.id}>
        <div className="doctor-monogram">{doctor.name.replace("Dra. ", "").replace("Dr. ", "").split(" ").map((part) => part[0]).slice(0, 2).join("")}</div>
        <div><h3>{doctor.name}</h3><p>{doctor.specialty}</p><small>{doctor.crm}</small></div>
        <div className="doctor-meta"><span><MapPin size={16} /> {doctor.unit}</span><span><i /> {doctor.insurers.join(" · ")}</span></div>
        <Link href="/agendar" className="text-link">Ver agenda <ArrowRight size={17} /></Link>
      </article>
    ))}
  </div>;
}
