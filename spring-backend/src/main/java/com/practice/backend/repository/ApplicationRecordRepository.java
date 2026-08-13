package com.practice.backend.repository;

import com.practice.backend.model.ApplicationRecord;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ApplicationRecordRepository extends JpaRepository<ApplicationRecord, Long> {
}
