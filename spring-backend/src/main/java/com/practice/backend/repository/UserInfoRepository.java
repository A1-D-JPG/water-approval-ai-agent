package com.practice.backend.repository;

import com.practice.backend.model.UserInfo;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface UserInfoRepository extends JpaRepository<UserInfo, Long> {
    Optional<UserInfo> findByUsername(String username);

    boolean existsByIdentityNo(String identityNo);

    boolean existsByCreditCode(String creditCode);

    boolean existsByPhone(String phone);

    boolean existsByEmail(String email);

    long countByRole(String role);
}
