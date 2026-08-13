package com.practice.backend.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

@Entity
@Table(name = "application")
public class ApplicationRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "applicant_name", nullable = false, length = 100)
    private String applicantName;

    @Column(name = "id_number", nullable = false, length = 32)
    private String idNumber;

    @Column(name = "applicant_user_id")
    private Long applicantUserId;

    @Column(name = "project_name", length = 200)
    private String projectName;

    @Column(name = "water_location", length = 300)
    private String waterLocation;

    @Column(name = "water_use", length = 100)
    private String waterUse;

    @Column(name = "industry_category", length = 100)
    private String industryCategory;

    @Column(name = "contact_phone", length = 32)
    private String contactPhone;

    @Column(name = "status", nullable = false, length = 20)
    private String status;

    @Column(name = "submission_time", nullable = false)
    private LocalDateTime submissionTime;

    @Column(name = "file_path", length = 2000)
    private String filePath;

    @Lob
    @Column(name = "review_result", columnDefinition = "LONGTEXT")
    private String reviewResult;

    @Column(name = "review_time")
    private LocalDateTime reviewTime;

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getApplicantName() {
        return applicantName;
    }

    public void setApplicantName(String applicantName) {
        this.applicantName = applicantName;
    }

    public String getIdNumber() {
        return idNumber;
    }

    public void setIdNumber(String idNumber) {
        this.idNumber = idNumber;
    }

    public Long getApplicantUserId() {
        return applicantUserId;
    }

    public void setApplicantUserId(Long applicantUserId) {
        this.applicantUserId = applicantUserId;
    }

    public String getProjectName() {
        return projectName;
    }

    public void setProjectName(String projectName) {
        this.projectName = projectName;
    }

    public String getWaterLocation() {
        return waterLocation;
    }

    public void setWaterLocation(String waterLocation) {
        this.waterLocation = waterLocation;
    }

    public String getWaterUse() {
        return waterUse;
    }

    public void setWaterUse(String waterUse) {
        this.waterUse = waterUse;
    }

    public String getIndustryCategory() {
        return industryCategory;
    }

    public void setIndustryCategory(String industryCategory) {
        this.industryCategory = industryCategory;
    }

    public String getContactPhone() {
        return contactPhone;
    }

    public void setContactPhone(String contactPhone) {
        this.contactPhone = contactPhone;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public LocalDateTime getSubmissionTime() {
        return submissionTime;
    }

    public void setSubmissionTime(LocalDateTime submissionTime) {
        this.submissionTime = submissionTime;
    }

    public String getFilePath() {
        return filePath;
    }

    public void setFilePath(String filePath) {
        this.filePath = filePath;
    }

    public String getReviewResult() {
        return reviewResult;
    }

    public void setReviewResult(String reviewResult) {
        this.reviewResult = reviewResult;
    }

    public LocalDateTime getReviewTime() {
        return reviewTime;
    }

    public void setReviewTime(LocalDateTime reviewTime) {
        this.reviewTime = reviewTime;
    }
}
