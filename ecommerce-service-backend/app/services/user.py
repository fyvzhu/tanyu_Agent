"""
用户服务（异步版本）
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import (
    UserRepository,
    UserMeasurementsRepository,
    UserProfileRepository,
    UserPreferencesRepository,
)
from app.schemas import (
    UserProfileResponse,
    UserMeasurementsRequest,
    UserMeasurementsResponse,
    UpdateProfileRequest,
    UserProfileDetailResponse,
    UserProfileDetailUpdate,
    UserPreferencesResponse,
    UserPreferencesUpdate,
)
from app.models import User, UserMeasurements, UserProfile, UserPreferences


class UserService:
    """用户服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)
        self.measurements_repo = UserMeasurementsRepository(db)

    async def get_user_profile(self, user_id: str) -> UserProfileResponse | None:
        """
        获取用户资料

        Args:
            user_id: 用户 ID

        Returns:
            用户资料或 None
        """
        user = await self.user_repo.get_by_user_id(user_id)
        if not user:
            return None

        return UserProfileResponse(
            user_id=user.user_id,
            username=user.username,
            nickname=user.nickname,
            phone_number_masked=self._mask_phone(user.phone_number),
            email_masked=self._mask_email(user.email),
            level=user.level,
        )

    async def update_profile(self, user_id: str, data: UpdateProfileRequest) -> UserProfileResponse:
        """
        更新用户资料

        Args:
            user_id: 用户 ID
            data: 更新数据

        Returns:
            更新后的用户资料

        Raises:
            ValueError: 用户不存在
        """
        user = await self.user_repo.get_by_user_id(user_id)
        if not user:
            raise ValueError("用户不存在")

        # 更新字段
        if data.nickname is not None:
            user.nickname = data.nickname
        if data.phone_number is not None:
            user.phone_number = data.phone_number
        if data.email is not None:
            user.email = data.email

        await self.db.commit()

        return UserProfileResponse(
            user_id=user.user_id,
            username=user.username,
            nickname=user.nickname,
            phone_number_masked=self._mask_phone(user.phone_number),
            email_masked=self._mask_email(user.email),
            level=user.level,
        )

    async def get_user_measurements(self, user_id: str) -> UserMeasurementsResponse | None:
        """
        获取用户体型数据

        Args:
            user_id: 用户 ID

        Returns:
            体型数据或 None
        """
        measurements = await self.measurements_repo.get_by_user_id(user_id)
        if not measurements:
            return None

        return UserMeasurementsResponse(
            user_id=measurements.user_id,
            height_cm=measurements.height_cm,
            weight_kg=measurements.weight_kg,
            bust_cm=measurements.bust_cm,
            waist_cm=measurements.waist_cm,
            hip_cm=measurements.hip_cm,
            shoulder_cm=measurements.shoulder_cm,
            foot_length_cm=measurements.foot_length_cm,
            foot_width_cm=measurements.foot_width_cm,
            updated_at=measurements.updated_at.isoformat() if measurements.updated_at else None,
        )

    async def update_measurements(self, user_id: str, data: UserMeasurementsRequest) -> UserMeasurementsResponse:
        """
        更新用户体型数据

        Args:
            user_id: 用户 ID
            data: 体型数据

        Returns:
            更新后的体型数据
        """
        measurements = await self.measurements_repo.get_by_user_id(user_id)

        if not measurements:
            # 创建新记录
            measurements = UserMeasurements(
                user_id=user_id,
                height_cm=data.height_cm,
                weight_kg=data.weight_kg,
                bust_cm=data.bust_cm,
                waist_cm=data.waist_cm,
                hip_cm=data.hip_cm,
                shoulder_cm=data.shoulder_cm,
                foot_length_cm=data.foot_length_cm,
                foot_width_cm=data.foot_width_cm,
            )
            await self.measurements_repo.create(measurements)
            await self.db.commit()
        else:
            # 更新现有记录
            if data.height_cm is not None:
                measurements.height_cm = data.height_cm
            if data.weight_kg is not None:
                measurements.weight_kg = data.weight_kg
            if data.bust_cm is not None:
                measurements.bust_cm = data.bust_cm
            if data.waist_cm is not None:
                measurements.waist_cm = data.waist_cm
            if data.hip_cm is not None:
                measurements.hip_cm = data.hip_cm
            if data.shoulder_cm is not None:
                measurements.shoulder_cm = data.shoulder_cm
            if data.foot_length_cm is not None:
                measurements.foot_length_cm = data.foot_length_cm
            if data.foot_width_cm is not None:
                measurements.foot_width_cm = data.foot_width_cm

            await self.db.commit()

        return UserMeasurementsResponse(
            user_id=measurements.user_id,
            height_cm=measurements.height_cm,
            weight_kg=measurements.weight_kg,
            bust_cm=measurements.bust_cm,
            waist_cm=measurements.waist_cm,
            hip_cm=measurements.hip_cm,
            shoulder_cm=measurements.shoulder_cm,
            foot_length_cm=measurements.foot_length_cm,
            foot_width_cm=measurements.foot_width_cm,
            updated_at=measurements.updated_at.isoformat() if measurements.updated_at else None,
        )

    @staticmethod
    def _mask_phone(phone: str | None) -> str | None:
        """脱敏手机号：保留前3后4"""
        if not phone or len(phone) < 7:
            return phone
        return f"{phone[:3]}****{phone[-4:]}"

    @staticmethod
    def _mask_email(email: str | None) -> str | None:
        """脱敏邮箱：保留前2个字符和@后内容"""
        if not email or "@" not in email:
            return email
        username, domain = email.split("@", 1)
        if len(username) <= 2:
            return email
        return f"{username[:2]}****@{domain}"
